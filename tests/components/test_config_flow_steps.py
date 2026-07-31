"""End-to-end config, options, reconfigure and reauth flows."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData
import pytest

from custom_components.dsc_neo_itv2.const import (
    CONF_HOST,
    CONF_INSTALLER_CODE,
    CONF_INTEGRATION_ID,
    CONF_PORT,
    CONF_TYPE1_KEY,
    CONF_TYPE2_KEY,
    CONF_USER_PIN,
    DOMAIN,
)

INTEGRATION_ID = "123456789012"
GOOD_SECRETS = {
    CONF_TYPE2_KEY: "00112233445566778899aabbccddeeff",
    CONF_TYPE1_KEY: "",
    CONF_USER_PIN: "1234",
    CONF_INSTALLER_CODE: "5555",
}
LISTENER = {CONF_HOST: "0.0.0.0", CONF_PORT: 3072}


@pytest.fixture
def mock_setup_entry():
    """Stop the flow from actually binding a listener on entry creation."""
    with patch(
        "custom_components.dsc_neo_itv2.async_setup_entry", return_value=True
    ) as mock:
        yield mock


@pytest.fixture
def mock_preflight():
    with patch(
        "custom_components.dsc_neo_itv2.config_flow._preflight_bind",
        AsyncMock(return_value=None),
    ) as mock:
        yield mock


@pytest.fixture
def mock_probe():
    with patch(
        "custom_components.dsc_neo_itv2.config_flow._probe_first_panel",
        AsyncMock(
            return_value={"integration_id": INTEGRATION_ID, "encryption_type": 2}
        ),
    ) as mock:
        yield mock


async def start_flow(hass: HomeAssistant, source: str = config_entries.SOURCE_USER):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": source}
    )


async def advance_to_confirm(hass: HomeAssistant, flow_id: str, **listener):
    """Submit the listener form and return the resulting step.

    The wait step is transparent when the probe resolves immediately:
    HA starts the probe task eagerly, so the flow falls straight through
    to ``confirm``.
    """
    result = await hass.config_entries.flow.async_configure(
        flow_id, {**LISTENER, **listener}
    )
    if result.get("step_id") == "wait":
        await hass.async_block_till_done()
        result = await hass.config_entries.flow.async_configure(flow_id, {})
    return result


# --------------------------------------------------------------------------
# Happy path
# --------------------------------------------------------------------------


async def test_the_flow_opens_on_the_listener_form(hass: HomeAssistant):
    result = await start_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert not result["errors"]


async def test_a_full_install_creates_an_entry(
    hass: HomeAssistant, mock_setup_entry, mock_preflight, mock_probe
):
    result = await start_flow(hass)
    result = await advance_to_confirm(hass, result["flow_id"])
    assert result["step_id"] == "confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], dict(GOOD_SECRETS)
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"DSC Neo {INTEGRATION_ID}"
    assert result["data"] == {**LISTENER, CONF_INTEGRATION_ID: INTEGRATION_ID, **GOOD_SECRETS}
    assert len(mock_setup_entry.mock_calls) == 1


async def test_the_probe_is_given_the_configured_listener_address(
    hass: HomeAssistant, mock_setup_entry, mock_preflight, mock_probe
):
    result = await start_flow(hass)
    await advance_to_confirm(hass, result["flow_id"], **{CONF_PORT: 4000})
    assert mock_probe.await_args.args == ("0.0.0.0", 4000)


async def test_the_confirm_step_reports_what_the_panel_announced(
    hass: HomeAssistant, mock_setup_entry, mock_preflight, mock_probe
):
    result = await start_flow(hass)
    result = await advance_to_confirm(hass, result["flow_id"])
    assert result["description_placeholders"] == {
        "integration_id": INTEGRATION_ID,
        "encryption_type": "2",
    }


async def test_the_entry_is_keyed_on_the_panel_integration_id(
    hass: HomeAssistant, mock_setup_entry, mock_preflight, mock_probe
):
    result = await start_flow(hass)
    result = await advance_to_confirm(hass, result["flow_id"])
    await hass.config_entries.flow.async_configure(result["flow_id"], dict(GOOD_SECRETS))
    await hass.async_block_till_done()

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.unique_id == INTEGRATION_ID


# --------------------------------------------------------------------------
# Listener step validation
# --------------------------------------------------------------------------


@pytest.mark.parametrize("port", [0, -1, 65536, 99999])
async def test_out_of_range_ports_are_rejected_by_the_form_schema(
    hass: HomeAssistant, port
):
    """The number selector clamps the range before the handler ever runs."""
    result = await start_flow(hass)
    with pytest.raises(InvalidData):
        await hass.config_entries.flow.async_configure(
            result["flow_id"], {**LISTENER, CONF_PORT: port}
        )


@pytest.mark.parametrize("port", [1, 3072, 65535])
async def test_in_range_ports_are_accepted(
    hass: HomeAssistant, mock_setup_entry, mock_preflight, mock_probe, port
):
    result = await start_flow(hass)
    result = await advance_to_confirm(hass, result["flow_id"], **{CONF_PORT: port})
    assert result["step_id"] == "confirm"


@pytest.mark.parametrize(
    ("bind_error", "field", "shown"),
    [
        ("port_in_use", CONF_PORT, "port_in_use"),
        ("host_unavailable", CONF_HOST, "host_unavailable"),
        ("bind_denied", CONF_PORT, "bind_denied"),
        ("bind_failed", "base", "bind_failed"),
    ],
)
async def test_bind_problems_are_reported_on_the_listener_form(
    hass: HomeAssistant, bind_error, field, shown
):
    with patch(
        "custom_components.dsc_neo_itv2.config_flow._preflight_bind",
        AsyncMock(return_value=bind_error),
    ):
        result = await start_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], dict(LISTENER)
        )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {field: shown}


async def test_a_recoverable_bind_error_lets_the_user_retry(
    hass: HomeAssistant, mock_setup_entry, mock_probe
):
    result = await start_flow(hass)
    with patch(
        "custom_components.dsc_neo_itv2.config_flow._preflight_bind",
        AsyncMock(return_value="port_in_use"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], dict(LISTENER)
        )
    with patch(
        "custom_components.dsc_neo_itv2.config_flow._preflight_bind",
        AsyncMock(return_value=None),
    ):
        result = await advance_to_confirm(hass, result["flow_id"], **{CONF_PORT: 3073})
    assert result["step_id"] == "confirm"


# --------------------------------------------------------------------------
# Probe failures
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("exception", "reason"),
    [
        (TimeoutError(), "timeout_no_panel"),
        (OSError("address already in use"), "bind_failed"),
        (RuntimeError("boom"), "probe_failed"),
    ],
)
async def test_probe_failures_abort_with_a_specific_reason(
    hass: HomeAssistant, mock_preflight, exception, reason
):
    with patch(
        "custom_components.dsc_neo_itv2.config_flow._probe_first_panel",
        AsyncMock(side_effect=exception),
    ):
        result = await start_flow(hass)
        result = await advance_to_confirm(hass, result["flow_id"])

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == reason


async def test_the_wait_step_holds_while_the_probe_is_still_running(
    hass: HomeAssistant, mock_preflight
):
    async def never(host: str, port: int) -> dict:
        await asyncio.Event().wait()

    with patch(
        "custom_components.dsc_neo_itv2.config_flow._probe_first_panel", never
    ):
        result = await start_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], dict(LISTENER)
        )
        assert result["step_id"] == "wait"
        assert result["description_placeholders"] == {"host": "0.0.0.0", "port": "3072"}

        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        assert result["step_id"] == "wait"

        hass.config_entries.flow.async_abort(result["flow_id"])


# --------------------------------------------------------------------------
# Secret validation in the confirm step
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        (CONF_TYPE2_KEY, "nope", "invalid_type2_key"),
        (CONF_TYPE1_KEY, "abc", "invalid_type1_key"),
        (CONF_USER_PIN, "12", "invalid_user_pin"),
        (CONF_INSTALLER_CODE, "12", "invalid_installer_code"),
    ],
)
async def test_bad_secrets_keep_the_user_on_the_confirm_form(
    hass: HomeAssistant, mock_setup_entry, mock_preflight, mock_probe, field, value, error
):
    result = await start_flow(hass)
    result = await advance_to_confirm(hass, result["flow_id"])
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**GOOD_SECRETS, field: value}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "confirm"
    assert result["errors"] == {field: error}


async def test_the_user_can_correct_a_bad_secret_and_continue(
    hass: HomeAssistant, mock_setup_entry, mock_preflight, mock_probe
):
    result = await start_flow(hass)
    result = await advance_to_confirm(hass, result["flow_id"])
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**GOOD_SECRETS, CONF_TYPE2_KEY: "nope"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], dict(GOOD_SECRETS)
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY


# --------------------------------------------------------------------------
# Duplicates
# --------------------------------------------------------------------------


async def test_the_same_panel_cannot_be_added_twice(
    hass: HomeAssistant, mock_config_entry, mock_setup_entry, mock_preflight, mock_probe
):
    mock_config_entry.add_to_hass(hass)

    result = await start_flow(hass)
    result = await advance_to_confirm(hass, result["flow_id"])

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


# --------------------------------------------------------------------------
# Reauth
# --------------------------------------------------------------------------


async def test_reauth_shows_a_form_prefilled_with_the_current_codes(
    hass: HomeAssistant, mock_config_entry, mock_setup_entry
):
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reauth_flow(hass)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"


async def test_reauth_updates_the_entry_in_place(
    hass: HomeAssistant, mock_config_entry, mock_setup_entry
):
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reauth_flow(hass)

    new_key = "ffeeddccbbaa99887766554433221100"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**GOOD_SECRETS, CONF_TYPE2_KEY: new_key}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data[CONF_TYPE2_KEY] == new_key
    assert mock_config_entry.data[CONF_INTEGRATION_ID] == INTEGRATION_ID


async def test_reauth_rejects_a_malformed_key(
    hass: HomeAssistant, mock_config_entry, mock_setup_entry
):
    mock_config_entry.add_to_hass(hass)
    original = mock_config_entry.data[CONF_TYPE2_KEY]
    result = await mock_config_entry.start_reauth_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**GOOD_SECRETS, CONF_TYPE2_KEY: "nope"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_TYPE2_KEY: "invalid_type2_key"}
    assert mock_config_entry.data[CONF_TYPE2_KEY] == original


# --------------------------------------------------------------------------
# Reconfigure
# --------------------------------------------------------------------------


async def test_reconfigure_updates_the_listener_in_place(
    hass: HomeAssistant, mock_config_entry, mock_setup_entry, mock_preflight, mock_probe
):
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "user"

    result = await advance_to_confirm(hass, result["flow_id"], **{CONF_PORT: 4000})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], dict(GOOD_SECRETS)
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    assert mock_config_entry.data[CONF_PORT] == 4000


async def test_reconfigure_refuses_a_different_panel(
    hass: HomeAssistant, mock_config_entry, mock_setup_entry, mock_preflight
):
    mock_config_entry.add_to_hass(hass)

    with patch(
        "custom_components.dsc_neo_itv2.config_flow._probe_first_panel",
        AsyncMock(
            return_value={"integration_id": "999999999999", "encryption_type": 2}
        ),
    ):
        result = await mock_config_entry.start_reconfigure_flow(hass)
        result = await advance_to_confirm(hass, result["flow_id"])

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_panel_changed"
    assert mock_config_entry.data[CONF_INTEGRATION_ID] == INTEGRATION_ID
