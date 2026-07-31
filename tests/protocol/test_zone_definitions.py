"""Zone definition byte -> semantics mapping."""

from __future__ import annotations

import pytest
from zone_definitions import (
    FIRE_DEFINITIONS,
    KEYSWITCH_DEFINITIONS,
    TWENTY_FOUR_HOUR_DEFINITIONS,
    ZoneDefinition,
    definition_name,
    device_class_for_definition,
    is_24_hour_zone,
    is_fire_zone,
    is_keyswitch,
    is_sensor_zone,
)


def test_oem_definition_bytes_are_stable():
    assert ZoneDefinition.NullZone == 0
    assert ZoneDefinition.Delay1 == 1
    assert ZoneDefinition.Delay2 == 2
    assert ZoneDefinition.Instant == 3
    assert ZoneDefinition.Interior == 4
    assert ZoneDefinition.InteriorStayAway == 5


@pytest.mark.parametrize("definition", FIRE_DEFINITIONS)
def test_every_fire_definition_is_also_24_hour(definition):
    assert is_fire_zone(definition)
    assert is_24_hour_zone(definition)


@pytest.mark.parametrize("definition", KEYSWITCH_DEFINITIONS)
def test_keyswitches_are_not_sensor_zones(definition):
    assert is_keyswitch(definition)
    assert not is_sensor_zone(definition)


@pytest.mark.parametrize(
    "definition",
    [
        ZoneDefinition.Delay1,
        ZoneDefinition.Delay2,
        ZoneDefinition.Instant,
        ZoneDefinition.Interior,
        ZoneDefinition.DayZone,
        ZoneDefinition.NightZone,
    ],
)
def test_generic_intrusion_zones_are_bypassable_sensors(definition):
    assert is_sensor_zone(definition)
    assert not is_24_hour_zone(definition)
    assert not is_fire_zone(definition)
    assert not is_keyswitch(definition)


def test_the_null_zone_is_not_a_sensor():
    assert not is_sensor_zone(ZoneDefinition.NullZone)


@pytest.mark.parametrize(
    ("definition", "device_class"),
    [
        (ZoneDefinition.Standard24HourFire, "smoke"),
        (ZoneDefinition.AutoVerifiedFire, "smoke"),
        (ZoneDefinition.FireSupervisory, "problem"),
        (ZoneDefinition.CO24Hour, "carbon_monoxide"),
        (ZoneDefinition.Gas24Hour, "gas"),
        (ZoneDefinition.Flood24Hour, "moisture"),
        (ZoneDefinition.Heat24Hour, "heat"),
        (ZoneDefinition.LowTemperature24Hour, "cold"),
        (ZoneDefinition.Medical24Hour, "safety"),
        (ZoneDefinition.Panic24Hour, "safety"),
        (ZoneDefinition.LatchingTamper24Hour, "tamper"),
        (ZoneDefinition.DoorBell, "sound"),
    ],
)
def test_device_classes_for_unambiguous_definitions(definition, device_class):
    assert device_class_for_definition(definition) == device_class


@pytest.mark.parametrize(
    "definition",
    [
        ZoneDefinition.Delay1,
        ZoneDefinition.Delay2,
        ZoneDefinition.Instant,
        ZoneDefinition.Interior,
    ],
)
def test_ambiguous_definitions_defer_to_label_inference(definition):
    """Returning None tells the caller to fall back to the zone label."""
    assert device_class_for_definition(definition) is None


def test_unknown_definitions_have_no_device_class():
    assert device_class_for_definition(0xFE) is None


def test_definition_name_resolves_known_bytes():
    assert definition_name(ZoneDefinition.Delay1) == "Delay1"
    assert definition_name(0) == "NullZone"


def test_definition_name_preserves_unknown_bytes_in_hex():
    assert definition_name(0xFE) == "ZoneType_0xFE"


def test_the_24_hour_set_contains_every_fire_definition():
    assert FIRE_DEFINITIONS <= TWENTY_FOUR_HOUR_DEFINITIONS


def test_keyswitches_are_never_24_hour_zones():
    assert not (KEYSWITCH_DEFINITIONS & TWENTY_FOUR_HOUR_DEFINITIONS)
