"""Diagnostics redaction.

Diagnostics downloads are routinely pasted into public bug reports, so
every credential-bearing key must be redacted.
"""

from __future__ import annotations

from homeassistant.components.diagnostics import async_redact_data
import pytest

from custom_components.dsc_neo_itv2.const import (
    CONF_HOST,
    CONF_INSTALLER_CODE,
    CONF_INTEGRATION_ID,
    CONF_PORT,
    CONF_TYPE1_KEY,
    CONF_TYPE2_KEY,
    CONF_USER_PIN,
)
from custom_components.dsc_neo_itv2.diagnostics import REDACT_KEYS

SECRET_VALUES = {
    CONF_INTEGRATION_ID: "123456789012",
    CONF_TYPE2_KEY: "00112233445566778899aabbccddeeff",
    CONF_TYPE1_KEY: "12345678",
    CONF_USER_PIN: "1234",
    CONF_INSTALLER_CODE: "5555",
}


@pytest.mark.parametrize("key", sorted(SECRET_VALUES))
def test_every_credential_config_key_is_redacted(key):
    assert key in REDACT_KEYS


@pytest.mark.parametrize(
    "key",
    [
        "access_code",
        "type1_access_code",
        "type2_access_code_hex",
        "user_pin",
        "installer_code",
        "session_id",
    ],
)
def test_secret_shaped_aliases_are_also_redacted(key):
    assert key in REDACT_KEYS


@pytest.mark.parametrize("key", [CONF_HOST, CONF_PORT])
def test_non_secret_keys_are_not_redacted(key):
    assert key not in REDACT_KEYS


def test_no_secret_value_survives_redaction():
    redacted = async_redact_data(dict(SECRET_VALUES), REDACT_KEYS)
    assert not set(redacted.values()) & set(SECRET_VALUES.values())


def test_redaction_preserves_key_names():
    redacted = async_redact_data(dict(SECRET_VALUES), REDACT_KEYS)
    assert set(redacted) == set(SECRET_VALUES)


def test_nested_secrets_are_redacted_too():
    redacted = async_redact_data(
        {"entry": {"data": dict(SECRET_VALUES)}, CONF_HOST: "0.0.0.0"}, REDACT_KEYS
    )
    assert redacted[CONF_HOST] == "0.0.0.0"
    assert redacted["entry"]["data"][CONF_TYPE2_KEY] != SECRET_VALUES[CONF_TYPE2_KEY]
