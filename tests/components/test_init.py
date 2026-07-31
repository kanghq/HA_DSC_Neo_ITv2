"""Config-entry setup, unload and service registration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
import pytest

from custom_components.dsc_neo_itv2.const import (
    CONF_HOST,
    CONF_INSTALLER_CODE,
    CONF_INTEGRATION_ID,
    CONF_PORT,
    CONF_TYPE1_KEY,
    CONF_TYPE2_KEY,
    DOMAIN,
)

SERVICES = {
    "bypass_zone",
    "quick_exit",
    "activate_fap",
    "reload_panel_config",
    "sensor_reset",
    "command_output",
    "set_date_time",
}


@pytest.fixture
def stub_coordinator():
    """Replace the coordinator with a stub that never opens a socket."""
    instance = MagicMock()
    instance.async_start = AsyncMock()
    instance.async_stop = AsyncMock()
    instance.zones = {}
    instance.partitions = {}
    instance.zone_definitions = {}
    instance.trouble_groups = {}
    instance.data = {}
    instance.last_update_success = True

    with patch(
        "custom_components.dsc_neo_itv2.DscNeoCoordinator", return_value=instance
    ) as factory:
        factory.instance = instance
        yield factory


async def setup_entry(hass: HomeAssistant, entry) -> bool:
    entry.add_to_hass(hass)
    result = await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return result


# --------------------------------------------------------------------------
# Setup
# --------------------------------------------------------------------------


async def test_the_entry_loads(hass: HomeAssistant, mock_config_entry, stub_coordinator):
    assert await setup_entry(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.LOADED


async def test_the_listener_is_started_once(
    hass: HomeAssistant, mock_config_entry, stub_coordinator
):
    await setup_entry(hass, mock_config_entry)
    stub_coordinator.instance.async_start.assert_awaited_once()


async def test_the_coordinator_is_built_from_the_entry_data(
    hass: HomeAssistant, mock_config_entry, stub_coordinator
):
    await setup_entry(hass, mock_config_entry)

    kwargs = stub_coordinator.call_args.kwargs
    assert kwargs["host"] == mock_config_entry.data[CONF_HOST]
    assert kwargs["port"] == mock_config_entry.data[CONF_PORT]
    assert kwargs["entry_id"] == mock_config_entry.entry_id
    assert kwargs["installer_code"] == mock_config_entry.data[CONF_INSTALLER_CODE]


async def test_the_session_settings_carry_the_panel_credentials(
    hass: HomeAssistant, mock_config_entry, stub_coordinator
):
    await setup_entry(hass, mock_config_entry)

    settings = stub_coordinator.call_args.kwargs["settings"]
    assert settings.integration_id == mock_config_entry.data[CONF_INTEGRATION_ID]
    assert settings.type2_access_code_hex == mock_config_entry.data[CONF_TYPE2_KEY]
    assert settings.type1_access_code == mock_config_entry.data[CONF_TYPE1_KEY]


async def test_the_coordinator_is_exposed_as_runtime_data(
    hass: HomeAssistant, mock_config_entry, stub_coordinator
):
    await setup_entry(hass, mock_config_entry)
    assert mock_config_entry.runtime_data is stub_coordinator.instance


async def test_an_empty_installer_code_is_normalised_to_none(
    hass: HomeAssistant, mock_config_entry, stub_coordinator
):
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry,
        data={**mock_config_entry.data, CONF_INSTALLER_CODE: ""},
    )
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert stub_coordinator.call_args.kwargs["installer_code"] is None


# --------------------------------------------------------------------------
# Setup failure
# --------------------------------------------------------------------------


async def test_a_bind_failure_leaves_the_entry_unloaded(
    hass: HomeAssistant, mock_config_entry, stub_coordinator
):
    stub_coordinator.instance.async_start.side_effect = OSError(
        "[Errno 98] address already in use"
    )
    assert not await setup_entry(hass, mock_config_entry)
    assert mock_config_entry.state is not ConfigEntryState.LOADED


# --------------------------------------------------------------------------
# Services
# --------------------------------------------------------------------------


@pytest.mark.parametrize("service", sorted(SERVICES))
async def test_services_are_registered_on_setup(
    hass: HomeAssistant, mock_config_entry, stub_coordinator, service
):
    assert not hass.services.has_service(DOMAIN, service)
    await setup_entry(hass, mock_config_entry)
    assert hass.services.has_service(DOMAIN, service)


async def test_no_services_are_registered_when_setup_fails(
    hass: HomeAssistant, mock_config_entry, stub_coordinator
):
    stub_coordinator.instance.async_start.side_effect = OSError("nope")
    await setup_entry(hass, mock_config_entry)
    assert not any(hass.services.has_service(DOMAIN, s) for s in SERVICES)


# --------------------------------------------------------------------------
# Unload
# --------------------------------------------------------------------------


async def test_the_entry_unloads_cleanly(
    hass: HomeAssistant, mock_config_entry, stub_coordinator
):
    await setup_entry(hass, mock_config_entry)

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


async def test_unloading_stops_the_listener(
    hass: HomeAssistant, mock_config_entry, stub_coordinator
):
    await setup_entry(hass, mock_config_entry)
    await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    stub_coordinator.instance.async_stop.assert_awaited_once()


async def test_unloading_the_last_entry_removes_the_services(
    hass: HomeAssistant, mock_config_entry, stub_coordinator
):
    await setup_entry(hass, mock_config_entry)
    await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert not any(hass.services.has_service(DOMAIN, s) for s in SERVICES)


async def test_the_entry_can_be_reloaded(
    hass: HomeAssistant, mock_config_entry, stub_coordinator
):
    await setup_entry(hass, mock_config_entry)

    assert await hass.config_entries.async_reload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert stub_coordinator.instance.async_stop.await_count == 1
    assert stub_coordinator.instance.async_start.await_count == 2
