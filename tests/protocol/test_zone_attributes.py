"""Zone attribute bitfield decoding."""

from __future__ import annotations

import pytest
from zone_attributes import (
    ZoneEventReporting,
    ZoneFunctionalAttribute,
    ZonePhysicalAttribute,
    decode_event_reporting,
    decode_functional_attributes,
    decode_physical_attributes,
)


@pytest.mark.parametrize(
    ("decode", "flag_cls"),
    [
        (decode_functional_attributes, ZoneFunctionalAttribute),
        (decode_physical_attributes, ZonePhysicalAttribute),
        (decode_event_reporting, ZoneEventReporting),
    ],
)
def test_zero_decodes_to_no_flags(decode, flag_cls):
    assert decode(0) == []


@pytest.mark.parametrize(
    ("decode", "flag_cls"),
    [
        (decode_functional_attributes, ZoneFunctionalAttribute),
        (decode_physical_attributes, ZonePhysicalAttribute),
        (decode_event_reporting, ZoneEventReporting),
    ],
)
def test_each_single_bit_decodes_to_its_own_name(decode, flag_cls):
    for member in flag_cls:
        assert decode(int(member)) == [member.name]


@pytest.mark.parametrize(
    ("decode", "flag_cls"),
    [
        (decode_functional_attributes, ZoneFunctionalAttribute),
        (decode_physical_attributes, ZonePhysicalAttribute),
        (decode_event_reporting, ZoneEventReporting),
    ],
)
def test_every_defined_bit_is_reported_when_all_are_set(decode, flag_cls):
    all_bits = 0
    for member in flag_cls:
        all_bits |= int(member)
    assert set(decode(all_bits)) == {m.name for m in flag_cls}


def test_functional_attributes_combine():
    assert decode_functional_attributes(0x09) == ["Audible", "Bypassable"]


def test_physical_attributes_combine():
    decoded = decode_physical_attributes(
        int(ZonePhysicalAttribute.NormallyClosedLoop) | int(ZonePhysicalAttribute.TwoWayAudio)
    )
    assert decoded == ["NormallyClosedLoop", "TwoWayAudio"]


def test_event_reporting_combines():
    decoded = decode_event_reporting(
        int(ZoneEventReporting.Alarm) | int(ZoneEventReporting.Tamper)
    )
    assert decoded == ["Alarm", "Tamper"]


@pytest.mark.parametrize(
    "decode",
    [decode_functional_attributes, decode_physical_attributes, decode_event_reporting],
)
def test_undefined_bits_are_ignored_rather_than_raising(decode):
    assert isinstance(decode(0xFF), list)


@pytest.mark.parametrize(
    "flag_cls",
    [ZoneFunctionalAttribute, ZonePhysicalAttribute, ZoneEventReporting],
)
def test_flag_values_are_distinct_single_bits(flag_cls):
    values = [int(m) for m in flag_cls]
    assert len(values) == len(set(values))
    assert all(v and not (v & (v - 1)) for v in values)
