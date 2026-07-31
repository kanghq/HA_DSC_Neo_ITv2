"""Zone label -> device_class heuristics."""

from __future__ import annotations

import pytest
from zone_labels import infer_device_class


@pytest.mark.parametrize(
    ("label", "device_class"),
    [
        ("Smoke Detector", "smoke"),
        ("Basement Fire", "smoke"),
        ("Attic Heat", "heat"),
        ("Natural Gas", "gas"),
        ("Propane Detector", "gas"),
        ("Living Room Glass", "vibration"),
        ("Shock Sensor", "vibration"),
        ("Basement Water", "moisture"),
        ("Sump Leak", "moisture"),
        ("Pipe Freeze", "cold"),
        ("Hall Motion", "motion"),
        ("Upstairs PIR", "motion"),
        ("Garage Door", "garage_door"),
        ("Front Door", "door"),
        ("Side Entry", "door"),
        ("Kitchen Window", "window"),
        ("Patio Slider", "window"),
        ("Panel Tamper", "tamper"),
        ("Panic Button", "safety"),
    ],
)
def test_keyword_inference(label, device_class):
    assert infer_device_class(label) == device_class


@pytest.mark.parametrize(
    "label",
    ["CO", "Basement CO", "CO Detector", "Carbon Monoxide", "Upstairs Carbon Monoxide Det"],
)
def test_carbon_monoxide_is_not_gas(label):
    """"gas" is combustible gas and shows the wrong icon for a CO head.

    The old table matched on the substring "co " with a trailing space,
    so a zone called plainly "CO" never matched at all and came out as
    a door contact.
    """
    assert infer_device_class(label) == "carbon_monoxide"


@pytest.mark.parametrize(
    ("label", "device_class"),
    [
        # The last recognised word wins: these are contacts on a door or
        # a window, not glassbreaks or generic entry points.
        ("Sliding Glass Door", "door"),
        ("Patio Glass Door", "door"),
        ("Entry Window", "window"),
        ("Entrance Window", "window"),
        # ...but an actual glassbreak is still vibration.
        ("Glass Break LR", "vibration"),
        ("Glassbreak", "vibration"),
    ],
)
def test_the_last_word_decides(label, device_class):
    assert infer_device_class(label) == device_class


@pytest.mark.parametrize(
    ("label", "device_class"),
    [("French Doors", "door"), ("Bedroom Windows", "window"), ("Hall Motions", "motion")],
)
def test_plurals_match(label, device_class):
    assert infer_device_class(label) == device_class


@pytest.mark.parametrize(
    "label",
    [
        None,
        "",
        "   ",
        "Zone 14",
        "Corner",           # contains "co", but is not a CO detector
        "Basement Temperature",
    ],
)
def test_unknown_labels_fall_back_to_opening(label):
    assert infer_device_class(label) == "opening"


def test_matching_is_case_insensitive():
    assert infer_device_class("FRONT DOOR") == infer_device_class("front door") == "door"


def test_surrounding_whitespace_is_ignored():
    assert infer_device_class("   Front Door   ") == "door"


def test_the_more_specific_garage_door_rule_wins_over_door():
    assert infer_device_class("Garage Door") == "garage_door"


@pytest.mark.parametrize("label", [None, "", "   ", "Zone 12", "Aux Input"])
def test_unrecognised_labels_fall_back_to_opening(label):
    assert infer_device_class(label) == "opening"


def test_the_result_is_always_a_string():
    for label in (None, "", "Front Door", "\u00e9\u00e8\u00ea"):
        assert isinstance(infer_device_class(label), str)
