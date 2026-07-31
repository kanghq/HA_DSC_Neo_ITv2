"""Switch platform: per-zone bypass toggles.

Each enabled, non-24-hour, non-keyswitch zone gets one ``switch``
entity. Turning the switch on tells the panel to bypass the zone for
the next arm cycle (and stays on until either an arm/disarm cycle
clears it on the panel side or the user toggles it off explicitly).

24-hour and keyswitch zones are intentionally excluded:
  * 24-hour zones (fire, gas, panic, ...) can't be bypassed via the
    standard ``[*][1]`` flow and shouldn't be exposed as bypass
    targets in HA.
  * Keyswitch zones are control inputs, not sensors.

Bypass state is sourced from ``ZoneState.is_bypassed`` (panel-pushed,
not stored locally) so the UI always reflects the panel's truth.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONN_STATE_CONNECTED,
    SIGNAL_CONNECTION_UPDATE,
    SIGNAL_NEW_ZONE,
    SIGNAL_ZONE_UPDATE,
)
from .coordinator import DscNeoCoordinator
from .zone_definitions import is_24_hour_zone, is_keyswitch

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DscNeoCoordinator = entry.runtime_data
    seen_zones: set[int] = set()

    def _eligible(zone_no: int) -> bool:
        if not coordinator.is_zone_enabled(zone_no):
            return False
        definition = coordinator.zone_definitions.get(zone_no, 0)
        if is_keyswitch(definition):
            return False
        if is_24_hour_zone(definition):
            return False
        return True

    @callback
    def _on_new_zone(zone_no: int) -> None:
        if zone_no in seen_zones:
            return
        if not _eligible(zone_no):
            return
        seen_zones.add(zone_no)
        async_add_entities([DscNeoZoneBypassSwitch(coordinator, entry, zone_no)])

    initial: list[SwitchEntity] = []
    for zone_no in sorted(coordinator.zones):
        if not _eligible(zone_no):
            continue
        seen_zones.add(zone_no)
        initial.append(DscNeoZoneBypassSwitch(coordinator, entry, zone_no))
    if initial:
        async_add_entities(initial)

    entry.async_on_unload(
        async_dispatcher_connect(
            hass, f"{SIGNAL_NEW_ZONE}_{entry.entry_id}", _on_new_zone,
        )
    )


class DscNeoZoneBypassSwitch(SwitchEntity):
    """A togglable bypass for one panel zone.

    On = zone is currently bypassed on the panel (won't trigger an
    intrusion alarm). Off = normal monitoring.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "zone_bypass"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: DscNeoCoordinator,
        entry: ConfigEntry,
        zone_number: int,
    ) -> None:
        self._coordinator = coordinator
        self._entry = entry
        self.zone_number = zone_number
        self._attr_unique_id = f"{entry.entry_id}_zone_{zone_number}_bypass"
        self._attr_device_info = coordinator.panel_device_info

    @property
    def name(self) -> str:
        zone = self._coordinator.zones.get(self.zone_number)
        base = zone.label if zone and zone.label else f"Zone {self.zone_number}"
        return f"{base} bypass"

    @property
    def is_on(self) -> bool:
        zone = self._coordinator.zones.get(self.zone_number)
        return bool(zone and zone.is_bypassed)

    @property
    def available(self) -> bool:
        if not self._coordinator.is_zone_enabled(self.zone_number):
            return False
        return self._coordinator.connection_state == CONN_STATE_CONNECTED

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        zone = self._coordinator.zones.get(self.zone_number)
        if zone is None:
            return {}
        return {
            "zone_number": zone.number,
            "label": zone.label,
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set_bypass(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set_bypass(False)

    async def _set_bypass(self, bypass: bool) -> None:
        try:
            await self._coordinator.async_bypass_zone(
                partition=1, zone=self.zone_number, bypass=bypass,
            )
        except RuntimeError as exc:
            raise HomeAssistantError(str(exc)) from exc

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
