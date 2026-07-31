"""Config-flow secret validation and manifest/metadata sanity checks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.dsc_neo_itv2.config_flow import _validate_secrets
from custom_components.dsc_neo_itv2.const import (
    CONF_INSTALLER_CODE,
    CONF_TYPE1_KEY,
    CONF_TYPE2_KEY,
    CONF_USER_PIN,
    DOMAIN,
)

COMPONENT_DIR = Path(__file__).resolve().parents[2] / "custom_components" / DOMAIN


def validate(type2="", type1="", pin="", installer=""):
    return _validate_secrets(type2, type1, pin, installer)


# --------------------------------------------------------------------------
# Type 2 key
# --------------------------------------------------------------------------


def test_a_valid_type2_key_is_accepted():
    assert validate(type2="00112233445566778899aabbccddeeff") == {}


def test_an_uppercase_type2_key_is_accepted():
    assert validate(type2="00112233445566778899AABBCCDDEEFF") == {}


def test_surrounding_whitespace_is_stripped():
    assert validate(type2="  " + "0" * 32 + "  ") == {}


@pytest.mark.parametrize("key", ["0" * 31, "0" * 33, "abc"])
def test_a_type2_key_of_the_wrong_length_is_rejected(key):
    assert validate(type2=key) == {CONF_TYPE2_KEY: "invalid_type2_key"}


def test_a_non_hex_type2_key_is_rejected():
    assert validate(type2="z" * 32) == {CONF_TYPE2_KEY: "invalid_type2_key"}


# --------------------------------------------------------------------------
# Type 1 key
# --------------------------------------------------------------------------


def test_a_valid_type1_key_is_accepted():
    assert validate(type1="12345678") == {}


@pytest.mark.parametrize("key", ["1234567", "123456789", "1234567a", "abcdefgh"])
def test_an_invalid_type1_key_is_rejected(key):
    assert validate(type1=key) == {CONF_TYPE1_KEY: "invalid_type1_key"}


# --------------------------------------------------------------------------
# User PIN and installer code
# --------------------------------------------------------------------------


@pytest.mark.parametrize("pin", ["1234", "12345", "123456"])
def test_pins_of_four_to_six_digits_are_accepted(pin):
    assert validate(pin=pin) == {}


@pytest.mark.parametrize("pin", ["123", "1234567", "12a4", "abcd"])
def test_invalid_pins_are_rejected(pin):
    assert validate(pin=pin) == {CONF_USER_PIN: "invalid_user_pin"}


@pytest.mark.parametrize("code", ["5555", "55555", "555555"])
def test_installer_codes_of_four_to_six_digits_are_accepted(code):
    assert validate(installer=code) == {}


@pytest.mark.parametrize("code", ["555", "5555555", "55a5"])
def test_invalid_installer_codes_are_rejected(code):
    assert validate(installer=code) == {CONF_INSTALLER_CODE: "invalid_installer_code"}


# --------------------------------------------------------------------------
# Optionality and error aggregation
# --------------------------------------------------------------------------


def test_all_secrets_are_optional():
    assert validate() == {}


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_values_are_treated_as_unset(blank):
    assert validate(type2=blank, type1=blank, pin=blank, installer=blank) == {}


def test_every_invalid_field_is_reported_at_once():
    assert validate(type2="bad", type1="bad", pin="bad", installer="bad") == {
        CONF_TYPE2_KEY: "invalid_type2_key",
        CONF_TYPE1_KEY: "invalid_type1_key",
        CONF_USER_PIN: "invalid_user_pin",
        CONF_INSTALLER_CODE: "invalid_installer_code",
    }


def test_error_keys_match_form_field_names():
    errors = validate(type2="bad")
    assert set(errors) <= {
        CONF_TYPE2_KEY,
        CONF_TYPE1_KEY,
        CONF_USER_PIN,
        CONF_INSTALLER_CODE,
    }


# --------------------------------------------------------------------------
# Translations must cover every error key the flow can emit
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def strings() -> dict:
    return json.loads((COMPONENT_DIR / "strings.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "error_key",
    [
        "invalid_type2_key",
        "invalid_type1_key",
        "invalid_user_pin",
        "invalid_installer_code",
    ],
)
def test_every_validation_error_has_a_translation(strings, error_key):
    assert error_key in strings["config"]["error"]


def test_english_translations_match_strings_json(strings):
    translations = json.loads(
        (COMPONENT_DIR / "translations" / "en.json").read_text(encoding="utf-8")
    )
    assert set(translations["config"]["error"]) >= set(strings["config"]["error"])


# ---------------------------------------------------------------------------
# Options flow
#
# Home Assistant made OptionsFlow.config_entry a read-only property and
# removed the setter in 2025.12, so an options flow that takes the entry
# in __init__ and assigns it raises AttributeError when the user opens
# "Configure". The flow must be constructed with no arguments and read
# the entry from the base class instead.
# ---------------------------------------------------------------------------


def test_the_options_flow_takes_no_constructor_arguments():
    from custom_components.dsc_neo_itv2.config_flow import DscNeoOptionsFlow

    assert "__init__" not in DscNeoOptionsFlow.__dict__


def test_the_options_flow_does_not_assign_config_entry():
    """Constructing must not touch the read-only ``config_entry`` property."""
    from homeassistant.config_entries import OptionsFlow

    from custom_components.dsc_neo_itv2 import config_flow as cf

    class ReadOnlyConfigEntry(OptionsFlow):
        """Stands in for Home Assistant 2025.12 and later."""

        @property
        def config_entry(self):
            return "entry-resolved-from-handler"

    original = cf.DscNeoOptionsFlow.__bases__
    cf.DscNeoOptionsFlow.__bases__ = (ReadOnlyConfigEntry,)
    try:
        flow = cf.DscNeoItV2ConfigFlow.async_get_options_flow(None)
        assert flow.config_entry == "entry-resolved-from-handler"
    finally:
        cf.DscNeoOptionsFlow.__bases__ = original
