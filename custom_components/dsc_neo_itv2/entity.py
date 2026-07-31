"""Shared entity base classes for the DSC Neo integration.

Every entity in this integration follows a small set of patterns:

  * Use ``coordinator.panel_device_info`` so they cluster under one
    HA device card.
  * Subscribe to one or more dispatcher signals to re-render on state
    change without polling.
  * Become unavailable when the panel is disconnected (except for
    diagnostic / config entities that are still meaningful while
    offline, like "Reload panel config").

This module centralises that boilerplate so the per-platform files
stay focused on the actual entity logic.
"""
from __future__ import annotations

from collections.abc import Iterable

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import (
    CONN_STATE_CONNECTED,
    SIGNAL_CONNECTION_UPDATE,
)
from .coordinator import DscNeoCoordinator


class DscNeoEntity(Entity):
    """Base class for every DSC Neo HA entity.

    Subclasses must set ``_attr_unique_id`` (and typically
    ``_attr_translation_key``, so ``strings.json`` supplies the name and
    ``icons.json`` the icon) and override :meth:`_signals` to list the
    dispatcher signal suffixes (not whole signal names) this entity
    should re-render on.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False

    #: When True the entity stays available even if the panel is
    #: disconnected (used for "Reload panel config" button, the
    #: connection-state sensor itself, and similar meta entities).
    _available_offline: bool = False

    def __init__(
        self, coordinator: DscNeoCoordinator, entry: ConfigEntry,
    ) -> None:
        self._coordinator = coordinator
        self._entry = entry
        self._attr_device_info = coordinator.panel_device_info

    # ------------------------------------------------------------------
    # availability
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        if self._available_offline:
            return True
        return self._coordinator.connection_state == CONN_STATE_CONNECTED

    # ------------------------------------------------------------------
    # dispatcher wiring
    # ------------------------------------------------------------------

    def _signals(self) -> Iterable[str]:
        """Return the dispatcher signal names this entity listens to.

        The connection-update signal is always added on top of these,
        so subclasses don't need to include it.

        Override in subclasses; default is no extra signals.
        """
        return ()

    async def async_added_to_hass(self) -> None:
        for signal in self._signals():
            self.async_on_remove(
                async_dispatcher_connect(
                    self.hass, signal, self.async_write_ha_state,
                )
            )
        # Always update on connection-state transitions so availability
        # / cached-state attributes refresh promptly.
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_CONNECTION_UPDATE}_{self._entry.entry_id}",
                self.async_write_ha_state,
            )
        )
