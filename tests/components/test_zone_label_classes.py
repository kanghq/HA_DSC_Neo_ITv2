"""Zone-label inference must only ever name real device classes.

Lives in the HA test tree, not ``tests/protocol``: the protocol job runs
without Home Assistant installed, so it cannot import the enum.
"""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
import pytest

from custom_components.dsc_neo_itv2.zone_labels import (
    _PHRASES,
    _WORDS,
    infer_device_class,
)


@pytest.mark.parametrize(("key", "value"), sorted(_WORDS.items()))
def test_every_word_maps_to_a_real_device_class(key, value):
    """A typo would silently downgrade the zone to "opening"."""
    assert BinarySensorDeviceClass(value)


@pytest.mark.parametrize(("key", "value"), _PHRASES)
def test_every_phrase_maps_to_a_real_device_class(key, value):
    assert BinarySensorDeviceClass(value)


def test_the_default_is_a_real_device_class():
    assert BinarySensorDeviceClass(infer_device_class(None)) is BinarySensorDeviceClass.OPENING
