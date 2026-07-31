"""Sensor platform: panel meta-info + per-partition health / count sensors.

Sensors exposed:

  * Firmware
  * Connection state
  * Panel time
  * Open zones / Bypassed zones (per partition)
  * Fire status (per partition) - ok / trouble / pre_alert / alarm
  * Burglary status (per partition) - disarmed / not_ready / ready /
    exit_delay / armed / entry_delay / alarm
  * System status (per partition) - disarmed / armed / trouble / alarm

The three per-partition status sensors mirror bosch_alarm's Fire /
Gas / Burglary trio so users moving between integrations get
familiar abstractions.
"""
from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import (
    SIGNAL_CONNECTION_UPDATE,
    SIGNAL_PARTITION_UPDATE,
)
from .coordinator import DscNeoCoordinator
from .entity import DscNeoEntity
from .zone_definitions import is_fire_zone

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DscNeoCoordinator = entry.runtime_data

    seen_partitions: set[int] = set()

    def _build_partition_entities(partition_no: int) -> list[SensorEntity]:
        if partition_no in seen_partitions:
            return []
        if not coordinator.is_partition_enabled(partition_no):
            return []
        seen_partitions.add(partition_no)
        return [
            cls(coordinator, entry, partition_no)
            for cls in _PARTITION_SENSOR_CLASSES
        ]

    initial: list[SensorEntity] = [
        DscNeoFirmwareSensor(coordinator, entry),
        DscNeoConnectionStateSensor(coordinator, entry),
        DscNeoPanelTimeSensor(coordinator, entry),
    ]
    for partition_no in sorted(coordinator.partitions):
        initial.extend(_build_partition_entities(partition_no))
    async_add_entities(initial)

    @callback
    def _check_new_partitions() -> None:
        new: list[SensorEntity] = []
        for partition_no in sorted(coordinator.partitions):
            new.extend(_build_partition_entities(partition_no))
        if new:
            async_add_entities(new)

    entry.async_on_unload(
        async_dispatcher_connect(
            hass, f"{SIGNAL_CONNECTION_UPDATE}_{entry.entry_id}",
            _check_new_partitions,
        )
    )


# ---------------------------------------------------------------------------
# Panel-wide diagnostic sensors
# ---------------------------------------------------------------------------


class _DiagnosticSensorBase(DscNeoEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _available_offline = True


class DscNeoFirmwareSensor(_DiagnosticSensorBase):
    # This is the COMMUNICATOR firmware (TL280/LE280/3G2080) reported in
    # the Connection_Open_Session handshake, NOT the alarm-panel
    # (HS2032/HS2128) firmware. The DSC integration protocol doesn't
    # expose the panel-side firmware as a discrete field; it's only
    # readable from the keypad's installer section [900].
    _attr_translation_key = "firmware"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_firmware"

    @property
    def native_value(self) -> str | None:
        return self._coordinator.panel_firmware


class DscNeoConnectionStateSensor(_DiagnosticSensorBase):
    _attr_translation_key = "connection_state"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["disconnected", "handshaking", "connected", "failed"]

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_connection_state"

    @property
    def native_value(self) -> str:
        return self._coordinator.connection_state

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "host": self._coordinator.host,
            "port": self._coordinator.port,
            "session_id": self._coordinator.panel_session_id,
        }


class DscNeoPanelTimeSensor(_DiagnosticSensorBase):
    """Panel-reported wall-clock time.

    The panel broadcasts its date/time periodically (and on request).
    The value is naive: the panel has no concept of time-zone: so
    we assume it is in HA's configured local zone and surface it as a
    TIMESTAMP-class sensor (aware ``datetime``). HA renders this as a
    relative "X seconds ago" in cards and, importantly, excludes it
    from long-term statistics so we don't generate a database row
    every second.

    Disabled by default: useful for verifying panel clock drift
    against your HA host, but most users don't need it on a dashboard.
    """
    _attr_translation_key = "panel_time"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_panel_time"

    @property
    def native_value(self) -> datetime | None:
        dt = self._coordinator.panel_datetime
        if dt is None:
            return None
        if dt.tzinfo is None:
            # Panel reports wall-clock with no zone; assume HA local.
            dt = dt.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
        return dt


# ---------------------------------------------------------------------------
# Per-partition sensors
# ---------------------------------------------------------------------------


class _PartitionSensorBase(DscNeoEntity, SensorEntity):
    """Shared base for per-partition sensors."""

    _kind: str = ""
    _label: str = ""

    def __init__(self, coordinator, entry, partition_number: int) -> None:
        super().__init__(coordinator, entry)
        self.partition_number = partition_number
        self._attr_unique_id = (
            f"{entry.entry_id}_partition_{partition_number}_{self._kind}"
        )
        # Named here rather than through ``strings.json`` because the
        # partition suffix is only wanted on multi-partition systems,
        # which a static translation cannot express. ``_attr_name``
        # takes precedence over the translation key, which stays set so
        # ``icons.json`` still applies.
        self._attr_name = (
            self._label if partition_number == 1
            else f"{self._label} (partition {partition_number})"
        )

    def _signals(self):
        return (
            f"{SIGNAL_PARTITION_UPDATE}_{self._entry.entry_id}_{self.partition_number}",
        )

    def _partition_zone_numbers(self) -> list[int]:
        """Zone numbers we believe belong to this partition.

        Delegates to :meth:`DscNeoCoordinator.zones_for_partition`,
        which consults the decoded partition-zone assignment table
        (sections [201]..[208]) when available and falls back to the
        legacy "partition 1 owns everything" heuristic otherwise.
        """
        return self._coordinator.zones_for_partition(self.partition_number)


class DscNeoOpenZonesCountSensor(_PartitionSensorBase):
    """Count of zones currently open in this partition."""
    _kind = "open_zones"
    _label = "Open zones"
    _attr_translation_key = "open_zones"
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int:
        zones = self._coordinator.zones
        return sum(
            1 for zn in self._partition_zone_numbers()
            if zn in zones and zones[zn].is_open
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        zones = self._coordinator.zones
        return {
            "open_zones": [
                {"zone": zn, "label": zones[zn].label}
                for zn in sorted(self._partition_zone_numbers())
                if zn in zones and zones[zn].is_open
            ],
        }


class DscNeoBypassedZonesCountSensor(_PartitionSensorBase):
    """Count of zones currently bypassed in this partition."""
    _kind = "bypassed_zones"
    _label = "Bypassed zones"
    _attr_translation_key = "bypassed_zones"
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int:
        zones = self._coordinator.zones
        return sum(
            1 for zn in self._partition_zone_numbers()
            if zn in zones and zones[zn].is_bypassed
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        zones = self._coordinator.zones
        return {
            "bypassed_zones": [
                {"zone": zn, "label": zones[zn].label}
                for zn in sorted(self._partition_zone_numbers())
                if zn in zones and zones[zn].is_bypassed
            ],
        }


# --- Rolled-up health enum sensors (Bosch-style) ---------------------------

FIRE_STATES = ["ok", "trouble", "pre_alert", "alarm"]
BURGLARY_STATES = [
    "disarmed", "not_ready", "ready",
    "exit_delay", "armed", "entry_delay", "alarm",
]
SYSTEM_STATES = ["ok", "armed", "trouble", "alarm"]


class DscNeoPartitionFireStatusSensor(_PartitionSensorBase):
    """Rolled-up fire-subsystem status for the partition.

    Priority (highest wins):
        alarm     - fire alarm currently active
        pre_alert - fire pre-alert verify window
        trouble   - any fire zone has a trouble / tamper / low-batt bit set
        ok        - otherwise
    """
    _kind = "fire_status"
    _label = "Fire status"
    _attr_translation_key = "fire_status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = FIRE_STATES

    @property
    def native_value(self) -> str:
        part = self._coordinator.partitions.get(self.partition_number)
        if part and part.is_fire_alarm:
            return "alarm"
        if part and part.is_fire_pre_alert:
            return "pre_alert"
        zones = self._coordinator.zones
        for zn in self._partition_zone_numbers():
            z = zones.get(zn)
            if z is None:
                continue
            if (z.is_trouble or z.is_tamper or z.is_low_battery) and is_fire_zone(
                self._coordinator.zone_definitions.get(zn, 0)
            ):
                return "trouble"
        return "ok"


class DscNeoPartitionBurglaryStatusSensor(_PartitionSensorBase):
    """Rolled-up burglary / arming state for the partition.

    Priority (highest wins):
        alarm        - burglary alarm active
        entry_delay  - someone tripped a delay zone and is keying in their code
        armed        - partition is currently armed
        exit_delay   - exit delay running after an arm command
        ready        - disarmed and ready to arm (no open zones)
        not_ready    - disarmed but at least one zone is open
        disarmed     - disarmed (state unknown for "ready")
    """
    _kind = "burglary_status"
    _label = "Burglary status"
    _attr_translation_key = "burglary_status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = BURGLARY_STATES

    @property
    def native_value(self) -> str:
        part = self._coordinator.partitions.get(self.partition_number)
        if part is None:
            return "disarmed"
        if part.is_burglary_alarm:
            return "alarm"
        if part.is_entry_delay:
            return "entry_delay"
        if part.is_armed:
            return "armed"
        if part.is_exit_delay:
            return "exit_delay"
        if part.is_ready:
            return "ready"
        # Disarmed but not flagged "ready" - check if any zone is open
        zones = self._coordinator.zones
        any_open = any(
            zones[zn].is_open
            for zn in self._partition_zone_numbers()
            if zn in zones
        )
        return "not_ready" if any_open else "disarmed"


class DscNeoPartitionSystemStatusSensor(_PartitionSensorBase):
    """Rolled-up overall status for this partition.

    Priority (highest wins):
        alarm    - any alarm condition on this partition
        trouble  - this partition has a trouble bit set
        armed    - partition armed (no alarm / trouble)
        ok       - disarmed and no troubles

    Note: only this partition's trouble bit is considered. System-wide
    troubles (AC, battery, comm, etc.) are exposed by the panel-level
    ``DscNeoTroubleAnyEntity`` and the per-group trouble binary_sensors,
    so we don't mix scopes here: otherwise an AC-trouble on the panel
    would flag every partition as in trouble even when each partition
    itself is fine.
    """
    _kind = "system_status"
    _label = "System status"
    _attr_translation_key = "system_status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = SYSTEM_STATES

    @property
    def native_value(self) -> str:
        part = self._coordinator.partitions.get(self.partition_number)
        if part is None:
            return "ok"
        if part.is_in_alarm:
            return "alarm"
        if part.is_trouble:
            return "trouble"
        if part.is_armed:
            return "armed"
        return "ok"


# Order = display order in the device card.
_PARTITION_SENSOR_CLASSES = (
    DscNeoPartitionSystemStatusSensor,
    DscNeoPartitionFireStatusSensor,
    DscNeoPartitionBurglaryStatusSensor,
    DscNeoOpenZonesCountSensor,
    DscNeoBypassedZonesCountSensor,
)
