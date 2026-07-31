"""DSC PowerSeries Neo ITv2 integration entry point."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .const import (
    CONF_HOST,
    CONF_INSTALLER_CODE,
    CONF_INTEGRATION_ID,
    CONF_PORT,
    CONF_TYPE1_KEY,
    CONF_TYPE2_KEY,
    CONF_USER_PIN,
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_TYPE2_KEY,
    DOMAIN,
)
from .coordinator import DscNeoConfigEntry, DscNeoCoordinator
from .dsc_itv2.messages import ModuleControlActivateFAP
from .dsc_itv2.session import ConnectionSettings

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.ALARM_CONTROL_PANEL,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.SWITCH,
]


# ---------------------------------------------------------------------------
# Service schemas
# ---------------------------------------------------------------------------

SERVICE_BYPASS_ZONE = "bypass_zone"
SERVICE_QUICK_EXIT = "quick_exit"
SERVICE_ACTIVATE_FAP = "activate_fap"
SERVICE_RELOAD_PANEL_CONFIG = "reload_panel_config"
SERVICE_SENSOR_RESET = "sensor_reset"
SERVICE_COMMAND_OUTPUT = "command_output"
SERVICE_SET_DATE_TIME = "set_date_time"

_RELOAD_PANEL_CONFIG_SCHEMA = vol.Schema({
    vol.Required("entry_id"): cv.string,
})

_BYPASS_ZONE_SCHEMA = vol.Schema({
    vol.Required("entry_id"): cv.string,
    vol.Required("partition"): vol.All(vol.Coerce(int), vol.Range(min=1, max=8)),
    vol.Required("zone"): vol.All(vol.Coerce(int), vol.Range(min=1, max=128)),
    vol.Required("bypass"): cv.boolean,
})

_QUICK_EXIT_SCHEMA = vol.Schema({
    vol.Required("entry_id"): cv.string,
    vol.Optional("partition", default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=8)),
})

_ACTIVATE_FAP_SCHEMA = vol.Schema({
    vol.Required("entry_id"): cv.string,
    vol.Optional("partition", default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=8)),
    vol.Required("type"): vol.In(["fire", "auxiliary", "panic"]),
})

_SENSOR_RESET_SCHEMA = vol.Schema({
    vol.Required("entry_id"): cv.string,
    vol.Optional("partition", default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=8)),
})

_COMMAND_OUTPUT_SCHEMA = vol.Schema({
    vol.Required("entry_id"): cv.string,
    vol.Optional("partition", default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=8)),
    vol.Required("output"): vol.All(vol.Coerce(int), vol.Range(min=1, max=4)),
})

_SET_DATE_TIME_SCHEMA = vol.Schema({
    vol.Required("entry_id"): cv.string,
    vol.Optional("datetime"): cv.datetime,
})

_FAP_TYPE_MAP = {"fire": 0, "auxiliary": 1, "panic": 2}


# ---------------------------------------------------------------------------
# Setup / unload
# ---------------------------------------------------------------------------


async def async_setup_entry(hass: HomeAssistant, entry: DscNeoConfigEntry) -> bool:
    """Set up DSC Neo ITv2 from a config entry."""
    data = entry.data
    settings = ConnectionSettings(
        integration_id=data.get(CONF_INTEGRATION_ID),
        type1_access_code=data.get(CONF_TYPE1_KEY),
        type2_access_code_hex=data.get(CONF_TYPE2_KEY, DEFAULT_TYPE2_KEY),
    )
    coordinator = DscNeoCoordinator(
        hass=hass,
        entry_id=entry.entry_id,
        settings=settings,
        host=data.get(CONF_HOST, DEFAULT_HOST),
        port=int(data.get(CONF_PORT, DEFAULT_PORT)),
        installer_code=data.get(CONF_INSTALLER_CODE, "") or None,
    )
    try:
        await coordinator.async_start()
    except OSError as exc:
        _LOGGER.error("Failed to bind ITv2 listener: %s", exc)
        return False

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Reload this entry whenever the user updates it via the options
    # flow. The listener is registered after setup so the initial setup
    # call doesn't itself trigger a reload.
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    # Register services once (idempotent across multiple config entries;
    # service handlers route via the ``entry_id`` parameter).
    _async_register_services(hass)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: DscNeoConfigEntry) -> None:
    """Reload the entry when its data changes (e.g. via the options flow)."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: DscNeoConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    coordinator: DscNeoCoordinator | None = getattr(entry, "runtime_data", None)
    if coordinator is not None:
        await coordinator.async_stop()
        entry.runtime_data = None  # type: ignore[assignment]
    # Remove services if no other entries remain loaded. We exclude
    # the entry currently being unloaded since its state hasn't
    # transitioned to NOT_LOADED yet at this point.
    remaining = [
        e for e in hass.config_entries.async_entries(DOMAIN)
        if e.entry_id != entry.entry_id and e.state is ConfigEntryState.LOADED
    ]
    if not remaining:
        _async_unregister_services(hass)
    return unload_ok


# ---------------------------------------------------------------------------
# Service handlers
# ---------------------------------------------------------------------------


def _get_coordinator(hass: HomeAssistant, entry_id: str) -> DscNeoCoordinator:
    entry = hass.config_entries.async_get_entry(entry_id)
    coord: DscNeoCoordinator | None = (
        getattr(entry, "runtime_data", None) if entry is not None else None
    )
    if coord is None:
        raise ServiceValidationError(
            f"No DSC Neo config entry with id={entry_id!r}"
        )
    return coord


async def _service_bypass_zone(call: ServiceCall) -> None:
    coord = _get_coordinator(call.hass, call.data["entry_id"])
    try:
        await coord.async_bypass_zone(
            partition=call.data["partition"],
            zone=call.data["zone"],
            bypass=call.data["bypass"],
        )
    except RuntimeError as exc:
        raise HomeAssistantError(str(exc)) from exc


async def _service_quick_exit(call: ServiceCall) -> None:
    coord = _get_coordinator(call.hass, call.data["entry_id"])
    try:
        conn = coord._require_connected()   # type: ignore[attr-defined]
        from .dsc_itv2.messages import ModuleControlPartitionQuickExit
        await conn.send_message(
            ModuleControlPartitionQuickExit(
                command_sequence=0, partition=call.data["partition"],
            )
        )
    except RuntimeError as exc:
        raise HomeAssistantError(str(exc)) from exc


async def _service_activate_fap(call: ServiceCall) -> None:
    coord = _get_coordinator(call.hass, call.data["entry_id"])
    fap_type = _FAP_TYPE_MAP[call.data["type"]]
    try:
        conn = coord._require_connected()   # type: ignore[attr-defined]
        await conn.send_message(
            ModuleControlActivateFAP(
                command_sequence=0,
                partition=call.data["partition"],
                fap_type=fap_type,
            )
        )
    except RuntimeError as exc:
        raise HomeAssistantError(str(exc)) from exc


async def _service_reload_panel_config(call: ServiceCall) -> None:
    coord = _get_coordinator(call.hass, call.data["entry_id"])
    ok = await coord.async_reload_panel_config()
    if not ok:
        raise HomeAssistantError(
            "Cannot reload panel config: installer code not configured for this entry"
        )


async def _service_sensor_reset(call: ServiceCall) -> None:
    coord = _get_coordinator(call.hass, call.data["entry_id"])
    entry = call.hass.config_entries.async_get_entry(call.data["entry_id"])
    stored_pin = (entry.data.get(CONF_USER_PIN, "") if entry else "") or ""
    try:
        await coord.async_command_output(
            output_number=2,
            partition=call.data["partition"],
            access_code=stored_pin,
        )
    except RuntimeError as exc:
        raise HomeAssistantError(str(exc)) from exc


async def _service_command_output(call: ServiceCall) -> None:
    coord = _get_coordinator(call.hass, call.data["entry_id"])
    entry = call.hass.config_entries.async_get_entry(call.data["entry_id"])
    stored_pin = (entry.data.get(CONF_USER_PIN, "") if entry else "") or ""
    try:
        await coord.async_command_output(
            output_number=call.data["output"],
            partition=call.data["partition"],
            access_code=stored_pin,
        )
    except RuntimeError as exc:
        raise HomeAssistantError(str(exc)) from exc


async def _service_set_date_time(call: ServiceCall) -> None:
    coord = _get_coordinator(call.hass, call.data["entry_id"])
    when = call.data.get("datetime")  # may be None - coordinator defaults to now()
    try:
        await coord.async_set_panel_datetime(when)
    except RuntimeError as exc:
        raise HomeAssistantError(str(exc)) from exc


def _async_register_services(hass: HomeAssistant) -> None:
    """Register services once; subsequent config entries reuse them."""
    if hass.services.has_service(DOMAIN, SERVICE_BYPASS_ZONE):
        return
    hass.services.async_register(
        DOMAIN, SERVICE_BYPASS_ZONE, _service_bypass_zone,
        schema=_BYPASS_ZONE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_QUICK_EXIT, _service_quick_exit,
        schema=_QUICK_EXIT_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_ACTIVATE_FAP, _service_activate_fap,
        schema=_ACTIVATE_FAP_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RELOAD_PANEL_CONFIG, _service_reload_panel_config,
        schema=_RELOAD_PANEL_CONFIG_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SENSOR_RESET, _service_sensor_reset,
        schema=_SENSOR_RESET_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_COMMAND_OUTPUT, _service_command_output,
        schema=_COMMAND_OUTPUT_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_DATE_TIME, _service_set_date_time,
        schema=_SET_DATE_TIME_SCHEMA,
    )


def _async_unregister_services(hass: HomeAssistant) -> None:
    for svc in (
        SERVICE_BYPASS_ZONE,
        SERVICE_QUICK_EXIT,
        SERVICE_ACTIVATE_FAP,
        SERVICE_RELOAD_PANEL_CONFIG,
        SERVICE_SENSOR_RESET,
        SERVICE_COMMAND_OUTPUT,
        SERVICE_SET_DATE_TIME,
    ):
        if hass.services.has_service(DOMAIN, svc):
            hass.services.async_remove(DOMAIN, svc)
