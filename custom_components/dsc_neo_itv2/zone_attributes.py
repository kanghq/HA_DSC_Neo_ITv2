"""Decoders for installer-mode zone attribute / event-reporting bytes.

Two installer-programming sections are decoded here:

  * ``[002][zone]``: "Zone Attributes". Two bytes per zone:
      - Byte 0: :class:`ZoneFunctionalAttribute` flags (audible, bypass,
        force-arm, swinger-shutdown, transmission-delay, ...).
      - Byte 1: :class:`ZonePhysicalAttribute` flags (NC loop, single
        EOL, double EOL, fast loop, two-way audio, holdup-verified).
  * ``[307][zone]``: *Zone Event Reporting*. One byte per zone listing
    which event categories the zone reports upstream (alarm,
    alarm-restore, tamper, tamper-restore, fault, fault-restore).

Source of truth: NeoHub ``ZoneAttributeSection`` /
``ZoneEventReportingSection`` (verified against DSC HS2032 installer
programming).
"""
from __future__ import annotations

from enum import IntFlag


class ZoneFunctionalAttribute(IntFlag):
    """Byte 0 of section ``[002][zone]``: zone behaviour flags."""
    Audible            = 0x01
    PulsedOrSteady     = 0x02
    DoorChime          = 0x04
    Bypassable         = 0x08
    ForceArmable       = 0x10
    SwingerShutdown    = 0x20
    TransmissionDelay  = 0x40
    BurglaryVerified   = 0x80


class ZonePhysicalAttribute(IntFlag):
    """Byte 1 of section ``[002][zone]``: wiring / loop flags."""
    NormallyClosedLoop = 0x01
    SingleEOLResistor  = 0x02
    DoubleEOLResistor  = 0x04
    FastLoopResponse   = 0x08
    TwoWayAudio        = 0x10
    HoldupVerified     = 0x20


class ZoneEventReporting(IntFlag):
    """Section ``[307][zone]``: event categories the zone reports."""
    Alarm         = 0x01
    AlarmRestore  = 0x02
    Tamper        = 0x04
    TamperRestore = 0x08
    Fault         = 0x10
    FaultRestore  = 0x20


def _flag_names(value: int, flag_cls: type[IntFlag]) -> list[str]:
    """Return the set-bit names of ``value`` in ``flag_cls``, in bit order."""
    out: list[str] = []
    for member in flag_cls:
        bit = int(member)
        # Skip composite values (IntFlag may synthesise OR'd members);
        # we only want single-bit primitives.
        if bit == 0 or (bit & (bit - 1)) != 0:
            continue
        if value & bit:
            out.append(member.name)
    return out


def decode_functional_attributes(byte: int) -> list[str]:
    """Decode byte 0 of section ``[002][zone]`` into flag names."""
    return _flag_names(byte & 0xFF, ZoneFunctionalAttribute)


def decode_physical_attributes(byte: int) -> list[str]:
    """Decode byte 1 of section ``[002][zone]`` into flag names."""
    return _flag_names(byte & 0xFF, ZonePhysicalAttribute)


def decode_event_reporting(byte: int) -> list[str]:
    """Decode section ``[307][zone]`` byte into flag names."""
    return _flag_names(byte & 0xFF, ZoneEventReporting)
