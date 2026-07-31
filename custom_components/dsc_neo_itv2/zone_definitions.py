"""DSC zone-definition (zone type) catalog and HA mapping.

The Neo panel stores each zone's "zone definition" (a.k.a. "zone type")
as a single byte in installer section ``[001][NNN]``. The byte tells
the panel how to interpret that zone: whether it's a fire loop, a
24-hour panic loop, a delay-1 door, etc.

This module:

  * Names every documented zone-definition value (mirrors
    NeoHub's ``ZoneDefinition`` enum and the HS2032 reference manual).
  * Maps each value to the most appropriate HA
    ``BinarySensorDeviceClass`` so users get the right icon /
    critical-notification behaviour without relying on the zone label.
  * Categorises each value (intrusion / fire / safety / 24h / control)
    so other modules can answer "is this a 24-hour zone?" or "should
    this zone appear in the bypass UI?" without re-hardcoding the list.

Source of truth:
  * NeoHub ``DSC.NeoHub.Services.PanelConfiguration.Sections.ZoneDefinition``
    (and the mirror in ``DSC.TLink.ConfigurationSections.ZoneDefinition``).
  * DSC HS2032 Reference Manual, "Zone Programming" tables.
"""
from __future__ import annotations

from enum import IntEnum


class ZoneDefinition(IntEnum):
    """DSC zone-definition byte values.

    Names match NeoHub's enum exactly so installer-mode reads can be
    cross-referenced against decompiled DLS5 source. Not every value
    is implemented on every panel firmware; unknown bytes are surfaced
    raw and treated as generic intrusion zones for safety.
    """
    NullZone = 0                       # Disabled: entity should not exist
    Delay1 = 1
    Delay2 = 2
    Instant = 3
    Interior = 4
    InteriorStayAway = 5
    DelayStayAway = 6
    Delayed24HourFire = 7
    Standard24HourFire = 8
    InstantStayAway = 9
    InteriorDelay = 10
    DayZone = 11
    NightZone = 12
    Burglary24Hour = 17
    BellBuzzer24Hour = 18
    Supervisory24Hour = 23
    SupervisoryBuzzer24Hour = 24
    AutoVerifiedFire = 25
    FireSupervisory = 27
    Gas24Hour = 40
    CO24Hour = 41
    Holdup24Hour = 42
    Panic24Hour = 43
    Heat24Hour = 45
    Medical24Hour = 46
    Emergency24Hour = 47
    Sprinkler24Hour = 48
    Flood24Hour = 49
    LatchingTamper24Hour = 51
    NonAlarm24Hour = 52
    QuickBypass24Hour = 53
    HighTemperature24Hour = 56
    LowTemperature24Hour = 57
    NonLatchingTamper24Hour = 60
    MomentaryKeyswitchArm = 66
    MaintainedKeyswitchArm = 67
    MomentaryKeyswitchDisarm = 68
    MaintainedKeyswitchDisarm = 69
    DoorBell = 71


# --- Category sets ---------------------------------------------------------
#
# These exist so callers can ask "is this fire?" without hardcoding the
# definition numbers. ``KEYSWITCH`` are control inputs (the user wires a
# physical switch to arm/disarm); they don't represent sensors and
# shouldn't get a ``binary_sensor`` entity.

FIRE_DEFINITIONS: frozenset[int] = frozenset({
    ZoneDefinition.Delayed24HourFire,
    ZoneDefinition.Standard24HourFire,
    ZoneDefinition.AutoVerifiedFire,
    ZoneDefinition.FireSupervisory,
})

# 24-hour zones are always live: they can't be bypassed via the normal
# arm/disarm cycle and shouldn't appear in the "bypass before arming"
# UI. Includes fire, gas/CO, panic/holdup, medical, supervisory, etc.
TWENTY_FOUR_HOUR_DEFINITIONS: frozenset[int] = frozenset({
    ZoneDefinition.Delayed24HourFire,
    ZoneDefinition.Standard24HourFire,
    ZoneDefinition.Burglary24Hour,
    ZoneDefinition.BellBuzzer24Hour,
    ZoneDefinition.Supervisory24Hour,
    ZoneDefinition.SupervisoryBuzzer24Hour,
    ZoneDefinition.AutoVerifiedFire,
    ZoneDefinition.FireSupervisory,
    ZoneDefinition.Gas24Hour,
    ZoneDefinition.CO24Hour,
    ZoneDefinition.Holdup24Hour,
    ZoneDefinition.Panic24Hour,
    ZoneDefinition.Heat24Hour,
    ZoneDefinition.Medical24Hour,
    ZoneDefinition.Emergency24Hour,
    ZoneDefinition.Sprinkler24Hour,
    ZoneDefinition.Flood24Hour,
    ZoneDefinition.LatchingTamper24Hour,
    ZoneDefinition.NonAlarm24Hour,
    ZoneDefinition.QuickBypass24Hour,
    ZoneDefinition.HighTemperature24Hour,
    ZoneDefinition.LowTemperature24Hour,
    ZoneDefinition.NonLatchingTamper24Hour,
})

# Keyswitch zones are inputs to the panel (a physical switch
# controls arming). They shouldn't be exposed as ``binary_sensor``s;
# they're better modelled as switches if at all.
KEYSWITCH_DEFINITIONS: frozenset[int] = frozenset({
    ZoneDefinition.MomentaryKeyswitchArm,
    ZoneDefinition.MaintainedKeyswitchArm,
    ZoneDefinition.MomentaryKeyswitchDisarm,
    ZoneDefinition.MaintainedKeyswitchDisarm,
})


# --- Mapping to HA device_class ------------------------------------------
#
# Returns the most specific HA ``BinarySensorDeviceClass`` string for
# each known zone definition. Returning ``None`` means "we don't have
# strong information from the type byte alone: fall back to label
# inference".

_DEVICE_CLASS_BY_DEFINITION: dict[int, str] = {
    # Fire
    ZoneDefinition.Delayed24HourFire:   "smoke",
    ZoneDefinition.Standard24HourFire:  "smoke",
    ZoneDefinition.AutoVerifiedFire:    "smoke",
    ZoneDefinition.FireSupervisory:     "problem",
    # Gas / CO
    ZoneDefinition.Gas24Hour:           "gas",
    ZoneDefinition.CO24Hour:            "carbon_monoxide",
    # Water
    ZoneDefinition.Sprinkler24Hour:     "moisture",
    ZoneDefinition.Flood24Hour:         "moisture",
    # Temperature
    ZoneDefinition.Heat24Hour:          "heat",
    ZoneDefinition.HighTemperature24Hour: "heat",
    ZoneDefinition.LowTemperature24Hour:  "cold",
    # Life-safety (medical / panic / holdup / emergency)
    ZoneDefinition.Medical24Hour:       "safety",
    ZoneDefinition.Holdup24Hour:        "safety",
    ZoneDefinition.Panic24Hour:         "safety",
    ZoneDefinition.Emergency24Hour:     "safety",
    # Tamper / supervisory
    ZoneDefinition.LatchingTamper24Hour:    "tamper",
    ZoneDefinition.NonLatchingTamper24Hour: "tamper",
    ZoneDefinition.Supervisory24Hour:       "problem",
    ZoneDefinition.SupervisoryBuzzer24Hour: "problem",
    # Burglary
    ZoneDefinition.Burglary24Hour:      "safety",
    ZoneDefinition.BellBuzzer24Hour:    "safety",
    # Doorbell
    ZoneDefinition.DoorBell:            "sound",
    # Intentionally no entry for the generic intrusion types
    # (Delay1, Delay2, Instant, Interior, DayZone, NightZone, ...). Those
    # could be doors or motion or glass-break and the label is the
    # only signal we have. Callers should fall back to label inference.
}


def device_class_for_definition(definition: int) -> str | None:
    """Return the HA ``BinarySensorDeviceClass`` string for a zone definition.

    Returns ``None`` for definitions where the type alone isn't
    informative (generic intrusion zones: caller should fall back to
    label inference).
    """
    return _DEVICE_CLASS_BY_DEFINITION.get(definition)


def is_fire_zone(definition: int) -> bool:
    """True if the definition is a fire / fire-supervisory zone."""
    return definition in FIRE_DEFINITIONS


def is_24_hour_zone(definition: int) -> bool:
    """True if the definition is always-live (24-hour) and not bypassable.

    Used to filter zones out of the bypass UI and to mark them as
    relevant regardless of partition arm state.
    """
    return definition in TWENTY_FOUR_HOUR_DEFINITIONS


def is_keyswitch(definition: int) -> bool:
    """True if the definition is a keyswitch input (arm/disarm control)."""
    return definition in KEYSWITCH_DEFINITIONS


def is_sensor_zone(definition: int) -> bool:
    """True if the definition is a real sensor (not a keyswitch / null).

    Caller should still consider definition == 0 (NullZone) separately
    via ``is_zone_enabled()`` on the coordinator.
    """
    if definition == 0:
        return False
    return definition not in KEYSWITCH_DEFINITIONS


def definition_name(definition: int) -> str:
    """Return the OEM enum name for a zone-definition byte.

    Falls back to ``ZoneType_<hex>`` for unknown bytes so users can
    cross-reference against installer manuals without us losing fidelity.
    """
    try:
        return ZoneDefinition(definition).name
    except ValueError:
        return f"ZoneType_0x{definition:02X}"
