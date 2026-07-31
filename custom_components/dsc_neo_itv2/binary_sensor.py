"""Binary sensor platform: zones + connectivity indicator."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONN_STATE_CONNECTED,
    SIGNAL_CONNECTION_UPDATE,
    SIGNAL_NEW_ZONE,
    SIGNAL_PARTITION_UPDATE,
    SIGNAL_TROUBLE_UPDATE,
    SIGNAL_ZONE_UPDATE,
)
from .coordinator import DscNeoCoordinator
from .dsc_itv2.messages import TROUBLE_GROUP_LABELS
from .zone_definitions import (
    definition_name,
    device_class_for_definition,
    is_24_hour_zone,
    is_fire_zone,
    is_keyswitch,
)
from .zone_labels import infer_device_class

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DscNeoCoordinator = entry.runtime_data
    seen_zones: set[int] = set()

    @callback
    def _on_new_zone(zone_no: int) -> None:
        if zone_no in seen_zones:
            return
        if not coordinator.is_zone_enabled(zone_no):
            return
        if is_keyswitch(coordinator.zone_definitions.get(zone_no, 0)):
            return
        seen_zones.add(zone_no)
        async_add_entities([DscNeoZoneEntity(coordinator, entry, zone_no)])

    initial: list[BinarySensorEntity] = []
    for zone_no in sorted(coordinator.zones):
        if not coordinator.is_zone_enabled(zone_no):
            continue
        # Skip keyswitch zones: they're control inputs, not sensors.
        if is_keyswitch(coordinator.zone_definitions.get(zone_no, 0)):
            continue
        seen_zones.add(zone_no)
        initial.append(DscNeoZoneEntity(coordinator, entry, zone_no))
    initial.append(DscNeoConnectionSensor(coordinator, entry))
    # Diagnostic trouble bitmap: one entity per documented group
    # (matches the panel's [*][2] trouble menu) plus an aggregate.
    initial.append(DscNeoTroubleAnyEntity(coordinator, entry))
    for group_id, group_label in TROUBLE_GROUP_LABELS.items():
        initial.append(
            DscNeoTroubleGroupEntity(coordinator, entry, group_id, group_label)
        )

    # Per-partition substate entities (alarm/fire-pre-alert/etc.).
    seen_partitions: set[int] = set()

    def _build_partition_entities(partition_no: int) -> list[BinarySensorEntity]:
        if partition_no in seen_partitions:
            return []
        if not coordinator.is_partition_enabled(partition_no):
            return []
        seen_partitions.add(partition_no)
        return [
            cls(coordinator, entry, partition_no)
            for cls in _PARTITION_SUBSTATE_CLASSES
        ]

    for partition_no in sorted(coordinator.partitions):
        initial.extend(_build_partition_entities(partition_no))

    async_add_entities(initial)

    @callback
    def _check_new_partitions() -> None:
        new: list[BinarySensorEntity] = []
        for partition_no in sorted(coordinator.partitions):
            new.extend(_build_partition_entities(partition_no))
        if new:
            async_add_entities(new)

    entry.async_on_unload(
        async_dispatcher_connect(
            hass, f"{SIGNAL_NEW_ZONE}_{entry.entry_id}", _on_new_zone,
        )
    )
    entry.async_on_unload(
        async_dispatcher_connect(
            hass, f"{SIGNAL_CONNECTION_UPDATE}_{entry.entry_id}",
            _check_new_partitions,
        )
    )


def _resolve_device_class(
    definition: int | None, label: str | None,
) -> BinarySensorDeviceClass:
    """Pick the best HA device_class for a zone.

    Resolution order:
        1. DSC zone-definition byte (most reliable: fire/gas/CO/water/etc.)
        2. Zone-label keyword inference ("motion", "door", "glass", ...)
        3. ``OPENING`` as a safe generic fallback.
    """
    if definition:
        from_def = device_class_for_definition(definition)
        if from_def:
            try:
                return BinarySensorDeviceClass(from_def)
            except ValueError:
                pass
    raw = infer_device_class(label)
    try:
        return BinarySensorDeviceClass(raw)
    except ValueError:
        return BinarySensorDeviceClass.OPENING


class DscNeoZoneEntity(BinarySensorEntity):
    """One HA binary_sensor per panel zone."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DscNeoCoordinator,
        entry: ConfigEntry,
        zone_number: int,
    ) -> None:
        self._coordinator = coordinator
        self._entry = entry
        self.zone_number = zone_number
        self._attr_unique_id = f"{entry.entry_id}_zone_{zone_number}"
        self._attr_device_info = coordinator.panel_device_info

    @property
    def name(self) -> str:
        zone = self._coordinator.zones.get(self.zone_number)
        if zone and zone.label:
            return zone.label
        return f"Zone {self.zone_number}"

    @property
    def device_class(self) -> BinarySensorDeviceClass | None:
        zone = self._coordinator.zones.get(self.zone_number)
        definition = self._coordinator.zone_definitions.get(self.zone_number, 0)
        return _resolve_device_class(
            definition, zone.label if zone else None,
        )

    @property
    def is_on(self) -> bool:
        zone = self._coordinator.zones.get(self.zone_number)
        return bool(zone and zone.is_open)

    @property
    def available(self) -> bool:
        # An entity becomes unavailable if either the panel-config
        # cache says this zone is disabled (e.g. it was set to NullZone
        # at the keypad and then "Reload panel config" was pressed) OR
        # the panel itself is currently disconnected.
        if not self._coordinator.is_zone_enabled(self.zone_number):
            return False
        return self._coordinator.connection_state == CONN_STATE_CONNECTED

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        zone = self._coordinator.zones.get(self.zone_number)
        if zone is None:
            return {}
        definition = self._coordinator.zone_definitions.get(self.zone_number, 0)
        # ``is_open`` is intentionally omitted: it duplicates ``is_on``.
        return {
            "zone_number": zone.number,
            "label": zone.label,
            "zone_definition": definition,
            "zone_type": definition_name(definition) if definition else None,
            "is_fire_zone": is_fire_zone(definition),
            "is_24_hour_zone": is_24_hour_zone(definition),
            "is_tamper": zone.is_tamper,
            "is_trouble": zone.is_trouble,
            "is_low_battery": zone.is_low_battery,
            "is_alarm": zone.is_alarm,
            "is_bypassed": zone.is_bypassed,
            "raw_status": f"0x{zone.raw_status:02X}",
        }

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_ZONE_UPDATE}_{self._entry.entry_id}_{self.zone_number}",
                self.async_write_ha_state,
            )
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_CONNECTION_UPDATE}_{self._entry.entry_id}",
                self.async_write_ha_state,
            )
        )


class DscNeoConnectionSensor(BinarySensorEntity):
    """Connectivity indicator: on = panel is currently connected."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "panel_connection"

    def __init__(
        self, coordinator: DscNeoCoordinator, entry: ConfigEntry,
    ) -> None:
        self._coordinator = coordinator
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_connection"
        self._attr_device_info = coordinator.panel_device_info

    @property
    def is_on(self) -> bool:
        return self._coordinator.connection_state == CONN_STATE_CONNECTED

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        # Firmware is exposed via DscNeoFirmwareSensor and the device
        # registry ``sw_version`` field; not duplicated here.
        return {
            "connection_state": self._coordinator.connection_state,
            "session_id": self._coordinator.panel_session_id,
            "host": self._coordinator.host,
            "port": self._coordinator.port,
        }

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_CONNECTION_UPDATE}_{self._entry.entry_id}",
                self.async_write_ha_state,
            )
        )


class _DscNeoTroubleBase(BinarySensorEntity):
    """Common plumbing for system-trouble binary_sensors."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, coordinator: DscNeoCoordinator, entry: ConfigEntry,
    ) -> None:
        self._coordinator = coordinator
        self._entry = entry
        self._attr_device_info = coordinator.panel_device_info

    @property
    def available(self) -> bool:
        return self._coordinator.connection_state == CONN_STATE_CONNECTED

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_TROUBLE_UPDATE}_{self._entry.entry_id}",
                self.async_write_ha_state,
            )
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_CONNECTION_UPDATE}_{self._entry.entry_id}",
                self.async_write_ha_state,
            )
        )


class DscNeoTroubleAnyEntity(_DscNeoTroubleBase):
    """Aggregate: on whenever any trouble group is active.

    Mirrors the panel's keypad ``Trouble`` LED so users can write a
    single automation that fires whenever anything goes wrong, then
    drill into per-group entities to see what.
    """

    _attr_translation_key = "system_trouble"

    def __init__(
        self, coordinator: DscNeoCoordinator, entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_trouble_any"

    @property
    def is_on(self) -> bool:
        return self._coordinator.trouble.any_active

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        groups = self._coordinator.trouble.groups
        return {
            "active_groups": [
                {
                    "group": gid,
                    "label": TROUBLE_GROUP_LABELS.get(gid, f"Trouble {gid:02d}"),
                    "bitmap": f"0x{val:02X}",
                }
                for gid, val in sorted(groups.items())
                if val != 0
            ],
            "raw_groups": {
                str(gid): f"0x{val:02X}" for gid, val in sorted(groups.items())
            },
        }


class DscNeoTroubleGroupEntity(_DscNeoTroubleBase):
    """One entity per documented trouble group (Trouble 01..12).

    Exposes the panel's per-group bitmap so an automation can react to,
    e.g., only AC trouble or only Communications trouble. The raw byte
    is surfaced as an attribute so users can correlate which sub-item
    is active against the manual's Table 4-4 until we decode the
    bit-to-item mapping per firmware.
    """

    _attr_translation_key = "trouble_group"

    def __init__(
        self,
        coordinator: DscNeoCoordinator,
        entry: ConfigEntry,
        group_id: int,
        group_label: str,
    ) -> None:
        super().__init__(coordinator, entry)
        self._group_id = group_id
        self._group_label = group_label
        self._attr_unique_id = f"{entry.entry_id}_trouble_group_{group_id:02d}"
        self._attr_translation_placeholders = {"group": group_label}

    @property
    def is_on(self) -> bool:
        return self._coordinator.trouble.is_group_active(self._group_id)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        val = self._coordinator.trouble.groups.get(self._group_id, 0)
        bits_set = [i for i in range(8) if val & (1 << i)]
        return {
            "group_id": self._group_id,
            "group_label": self._group_label,
            "bitmap": f"0x{val:02X}",
            "bits_set": bits_set,
        }


# ---------------------------------------------------------------------------
# Per-partition substate binary_sensors
# ---------------------------------------------------------------------------


class _DscNeoPartitionSubstateBase(BinarySensorEntity):
    """Common plumbing for per-partition substate binary_sensors."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    # Subclasses set these:
    _kind: str = ""              # used in unique_id
    _label: str = ""             # human label
    _attr_device_class: BinarySensorDeviceClass | None = None
    _attr_entity_category: EntityCategory | None = None

    def __init__(
        self,
        coordinator: DscNeoCoordinator,
        entry: ConfigEntry,
        partition_number: int,
    ) -> None:
        self._coordinator = coordinator
        self._entry = entry
        self.partition_number = partition_number
        self._attr_unique_id = (
            f"{entry.entry_id}_partition_{partition_number}_{self._kind}"
        )
        self._attr_device_info = coordinator.panel_device_info
        # Named here rather than through ``strings.json`` because the
        # partition suffix is only wanted on multi-partition systems,
        # which a static translation cannot express. ``_attr_name``
        # takes precedence over the translation key, which stays set so
        # ``icons.json`` still applies.
        self._attr_name = (
            self._label if partition_number == 1
            else f"{self._label} (partition {partition_number})"
        )

    @property
    def available(self) -> bool:
        return self._coordinator.connection_state == CONN_STATE_CONNECTED

    def _state_value(self) -> bool:
        raise NotImplementedError

    @property
    def is_on(self) -> bool:
        return self._state_value()

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_PARTITION_UPDATE}_{self._entry.entry_id}_{self.partition_number}",
                self.async_write_ha_state,
            )
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_CONNECTION_UPDATE}_{self._entry.entry_id}",
                self.async_write_ha_state,
            )
        )


class DscNeoPartitionAlarmAny(_DscNeoPartitionSubstateBase):
    """On when the partition is currently in any alarm condition."""
    _kind = "alarm"
    _label = "Alarm"
    _attr_translation_key = "partition_alarm"
    _attr_device_class = BinarySensorDeviceClass.SAFETY

    def _state_value(self) -> bool:
        part = self._coordinator.partitions.get(self.partition_number)
        return bool(part and part.is_in_alarm)


class DscNeoPartitionFireAlarm(_DscNeoPartitionSubstateBase):
    """On when the partition is in alarm and the cause is a fire zone."""
    _kind = "fire_alarm"
    _label = "Fire alarm"
    _attr_translation_key = "partition_fire_alarm"
    _attr_device_class = BinarySensorDeviceClass.SMOKE

    def _state_value(self) -> bool:
        part = self._coordinator.partitions.get(self.partition_number)
        return bool(part and part.is_fire_alarm)


class DscNeoPartitionBurglaryAlarm(_DscNeoPartitionSubstateBase):
    """On when the partition is in alarm and the cause is not a fire zone."""
    _kind = "burglary_alarm"
    _label = "Burglary alarm"
    _attr_translation_key = "partition_burglary_alarm"
    _attr_device_class = BinarySensorDeviceClass.SAFETY

    def _state_value(self) -> bool:
        part = self._coordinator.partitions.get(self.partition_number)
        return bool(part and part.is_burglary_alarm)


class DscNeoPartitionFirePreAlert(_DscNeoPartitionSubstateBase):
    """On during the fire pre-alert verify window before a full fire alarm."""
    _kind = "fire_pre_alert"
    _label = "Fire pre-alert"
    _attr_translation_key = "partition_fire_pre_alert"
    _attr_device_class = BinarySensorDeviceClass.SMOKE

    def _state_value(self) -> bool:
        part = self._coordinator.partitions.get(self.partition_number)
        return bool(part and part.is_fire_pre_alert)


class DscNeoPartitionAlarmInMemory(_DscNeoPartitionSubstateBase):
    """On when there is an alarm in memory (cleared by next arm cycle)."""
    _kind = "alarm_in_memory"
    _label = "Alarm in memory"
    _attr_translation_key = "partition_alarm_in_memory"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def _state_value(self) -> bool:
        part = self._coordinator.partitions.get(self.partition_number)
        return bool(part and part.is_alarm_in_memory)


class DscNeoPartitionTrouble(_DscNeoPartitionSubstateBase):
    """On when the partition has any trouble condition.

    Source bits (whichever arrives first wins):
      * ``ModulePartitionStatus`` status-byte-2 bit 0x02 (``TroublesPresent``)
      * Unsolicited cmd 0x023F (``NotificationPartitionTroubleStatus``)

    This is a coarse "something is wrong" indicator. Per-group detail
    (AC loss, low battery, cellular, ...) only populates when the panel
    firmware supports ``ModuleStatus_System_Trouble_Status_New``
    (cmd 0x0822); older TL280 firmware does not.
    """
    _kind = "trouble"
    _label = "Trouble"
    _attr_translation_key = "partition_trouble"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def _state_value(self) -> bool:
        part = self._coordinator.partitions.get(self.partition_number)
        return bool(part and part.is_trouble)


class DscNeoPartitionExitDelay(_DscNeoPartitionSubstateBase):
    """On during the exit-delay countdown after an arm command."""
    _kind = "exit_delay"
    _label = "Exit delay"
    _attr_translation_key = "partition_exit_delay"
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def _state_value(self) -> bool:
        part = self._coordinator.partitions.get(self.partition_number)
        return bool(part and part.is_exit_delay)


class DscNeoPartitionEntryDelay(_DscNeoPartitionSubstateBase):
    """On during the entry-delay countdown after a delay-zone trips."""
    _kind = "entry_delay"
    _label = "Entry delay"
    _attr_translation_key = "partition_entry_delay"
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def _state_value(self) -> bool:
        part = self._coordinator.partitions.get(self.partition_number)
        return bool(part and part.is_entry_delay)


class DscNeoPartitionReadyToArm(_DscNeoPartitionSubstateBase):
    """On when the partition is ready to arm (no open zones)."""
    _kind = "ready"
    _label = "Ready to arm"
    _attr_translation_key = "partition_ready"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def _state_value(self) -> bool:
        part = self._coordinator.partitions.get(self.partition_number)
        return bool(part and part.is_ready)


class DscNeoPartitionChimeEnabled(_DscNeoPartitionSubstateBase):
    """On when door chime is enabled for this partition."""
    _kind = "chime_enabled"
    _label = "Door chime enabled"
    _attr_translation_key = "partition_chime"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def _state_value(self) -> bool:
        part = self._coordinator.partitions.get(self.partition_number)
        return bool(part and part.is_door_chime_enabled)


class DscNeoPartitionProgrammingMode(_DscNeoPartitionSubstateBase):
    """On when the keypad is in installer programming mode."""
    _kind = "programming_mode"
    _label = "Installer programming"
    _attr_translation_key = "partition_programming"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def _state_value(self) -> bool:
        part = self._coordinator.partitions.get(self.partition_number)
        return bool(part and part.is_programming_mode)


# Order matters for friendly UI grouping; the alarm-related ones come first.
_PARTITION_SUBSTATE_CLASSES = (
    DscNeoPartitionAlarmAny,
    DscNeoPartitionFireAlarm,
    DscNeoPartitionBurglaryAlarm,
    DscNeoPartitionFirePreAlert,
    DscNeoPartitionAlarmInMemory,
    DscNeoPartitionTrouble,
    DscNeoPartitionExitDelay,
    DscNeoPartitionEntryDelay,
    DscNeoPartitionReadyToArm,
    DscNeoPartitionChimeEnabled,
    DscNeoPartitionProgrammingMode,
)
