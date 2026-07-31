"""Alarm-control-panel platform: one entity per panel partition."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
    CodeFormat,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_USER_PIN,
    CONN_STATE_CONNECTED,
    SIGNAL_CONNECTION_UPDATE,
    SIGNAL_PARTITION_UPDATE,
)
from .coordinator import DscNeoCoordinator
from .dsc_itv2.enums import ArmingMode

_LOGGER = logging.getLogger(__name__)

# Initially expose partition 1 only. When the panel reports a partition
# we hadn't seen, that's surfaced via SIGNAL_CONNECTION_UPDATE and we
# add it dynamically.
_DEFAULT_PARTITIONS = (1,)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DscNeoCoordinator = entry.runtime_data
    added: set[int] = set()

    @callback
    def _add_missing() -> None:
        new = []
        for n in sorted(coordinator.partitions):
            if n in added:
                continue
            if not coordinator.is_partition_enabled(n):
                continue
            new.append(DscNeoPartitionEntity(coordinator, entry, n))
        for ent in new:
            added.add(ent.partition_number)
        if new:
            async_add_entities(new)

    # Seed partition 1 if we don't yet know which are enabled. Once
    # installer-config arrives, _add_missing will fill in the rest.
    initial: list[DscNeoPartitionEntity] = []
    for n in _DEFAULT_PARTITIONS:
        if coordinator.is_partition_enabled(n):
            initial.append(DscNeoPartitionEntity(coordinator, entry, n))
    for ent in initial:
        added.add(ent.partition_number)
        coordinator._touch_partition(ent.partition_number)
    if initial:
        async_add_entities(initial)

    entry.async_on_unload(
        async_dispatcher_connect(
            hass, f"{SIGNAL_CONNECTION_UPDATE}_{entry.entry_id}", _add_missing,
        )
    )


class DscNeoPartitionEntity(AlarmControlPanelEntity):
    """One HA alarm-control-panel entity per panel partition."""

    _attr_has_entity_name = True
    _attr_translation_key = "partition"
    _attr_supported_features = (
        AlarmControlPanelEntityFeature.ARM_AWAY
        | AlarmControlPanelEntityFeature.ARM_HOME
        | AlarmControlPanelEntityFeature.ARM_NIGHT
    )

    def __init__(
        self,
        coordinator: DscNeoCoordinator,
        entry: ConfigEntry,
        partition_number: int,
    ) -> None:
        self._coordinator = coordinator
        self._entry = entry
        self.partition_number = partition_number
        self._attr_unique_id = f"{entry.entry_id}_partition_{partition_number}"
        self._attr_device_info = coordinator.panel_device_info
        # Pre-populate stored PIN; if absent, require code via UI per action.
        stored_pin = entry.data.get(CONF_USER_PIN, "") or ""
        self._stored_pin = stored_pin
        self._attr_code_arm_required = not bool(stored_pin)
        self._attr_code_format = CodeFormat.NUMBER if not stored_pin else None

    @property
    def name(self) -> str:
        part = self._coordinator.partitions.get(self.partition_number)
        return (part.label if part and part.label else f"Partition {self.partition_number}")

    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        part = self._coordinator.partitions.get(self.partition_number)
        if part is None:
            # No partition data yet. If we're connected, the panel
            # simply hasn't broadcast its status yet: assume disarmed
            # rather than showing "Unknown" in the UI. Once a real
            # ModulePartitionStatus or arming notification arrives,
            # this branch stops being reached.
            if self._coordinator.connection_state == CONN_STATE_CONNECTED:
                return AlarmControlPanelState.DISARMED
            return None
        if part.is_in_alarm:
            return AlarmControlPanelState.TRIGGERED
        if part.is_entry_delay:
            return AlarmControlPanelState.PENDING
        if part.is_exit_delay:
            return AlarmControlPanelState.ARMING
        if part.is_armed:
            mode = part.arming_mode
            if mode in (
                int(ArmingMode.StayArm),
                int(ArmingMode.StayArmWithNoEntryDelay),
                int(ArmingMode.InstantStayArm),
            ):
                return AlarmControlPanelState.ARMED_HOME
            if mode in (
                int(ArmingMode.NightArm),
                int(ArmingMode.NightArmWithNoEntryDelay),
            ):
                return AlarmControlPanelState.ARMED_NIGHT
            return AlarmControlPanelState.ARMED_AWAY
        return AlarmControlPanelState.DISARMED

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        part = self._coordinator.partitions.get(self.partition_number)
        if part is None:
            return {}
        # Zone membership comes from the decoded partition-zone assignment
        # table (sections [201]..[208]) when available; otherwise falls
        # back to "partition 1 owns every zone, others own none".
        partition_zones = set(
            self._coordinator.zones_for_partition(self.partition_number)
        )
        zones = self._coordinator.zones
        open_zones = [
            {"zone": zn, "label": zones[zn].label}
            for zn in sorted(partition_zones)
            if zn in zones and zones[zn].is_open
        ]
        bypassed_zones = [
            {"zone": zn, "label": zones[zn].label}
            for zn in sorted(partition_zones)
            if zn in zones and zones[zn].is_bypassed
        ]
        return {
            # Partition flags WITHOUT a dedicated binary_sensor are kept
            # here so they remain reachable from templates. Anything that
            # already has its own entity (is_ready, is_alarm_in_memory,
            # is_fire_alarm, is_burglary_alarm, is_fire_pre_alert,
            # is_trouble, is_programming_mode, is_door_chime_enabled) is
            # intentionally NOT duplicated - read those entities directly.
            "is_walk_test": part.is_walk_test,
            "is_audible_bell": part.is_audible_bell,
            "is_quick_exit": part.is_quick_exit,
            "is_bypassed": part.is_bypassed,
            "exit_delay_seconds": part.exit_delay_seconds,
            "entry_delay_seconds": part.entry_delay_seconds,
            "last_user_id": part.last_user_id,
            "open_zones": open_zones,
            "bypassed_zones": bypassed_zones,
            "raw_status1": f"0x{part.raw_status1:02X}",
            "raw_status2": f"0x{part.raw_status2:02X}",
            "raw_status3": f"0x{part.raw_status3:02X}",
        }

    @property
    def available(self) -> bool:
        return self._coordinator.connection_state == CONN_STATE_CONNECTED

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

    # ---- arm/disarm actions ----

    def _code(self, supplied: str | None) -> str:
        return (supplied or "").strip() or self._stored_pin

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        await self._coordinator.async_arm_partition(
            self.partition_number, ArmingMode.AwayArm, self._code(code),
        )

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        await self._coordinator.async_arm_partition(
            self.partition_number, ArmingMode.StayArm, self._code(code),
        )

    async def async_alarm_arm_night(self, code: str | None = None) -> None:
        await self._coordinator.async_arm_partition(
            self.partition_number, ArmingMode.NightArm, self._code(code),
        )

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        pin = self._code(code)
        if not pin:
            raise ValueError("disarm requires a user PIN")
        await self._coordinator.async_disarm_partition(self.partition_number, pin)
