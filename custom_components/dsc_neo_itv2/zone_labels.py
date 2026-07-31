"""Zone-label keyword inference for HA ``device_class``.

Given a panel-supplied zone label (e.g. "Front Door", "Kitchen Motion",
"Garage Door"), guess the most useful HA ``BinarySensorDeviceClass``
value. Returns ``"opening"`` as a safe default.

Matching runs in three passes, case-insensitively:

1. Multi-word phrases, which beat any single word. "Garage Door" is a
   ``garage_door``, not a ``door``.
2. The last recognised word, which in an installer's label is almost
   always the thing being sensed. "Sliding Glass Door" is a door
   contact, not a glassbreak; "Entry Window" is a window, not a door.
   A trailing "s" is tolerated so plurals match.
3. Failing both, ``"opening"``: an unspecified open/closed contact.

Whole words are compared, never substrings, so a zone called "Corner"
is not treated as a CO detector.

Source: hand-curated from common builder-installed Neo zone labels.
Adjust freely: there's no canonical list.
"""
from __future__ import annotations

import re

# Checked first, in order. Only needed where a single word would give a
# different (and worse) answer than the phrase as a whole.
_PHRASES: list[tuple[str, str]] = [
    ("garage door", "garage_door"),
    ("overhead door", "garage_door"),
    ("carbon monoxide", "carbon_monoxide"),
    ("glass break", "vibration"),
    ("glass-break", "vibration"),
]

# Single words. The last one present in a label wins, so ordering here
# is irrelevant; group them however reads best.
_WORDS: dict[str, str] = {
    # Smoke / fire / heat
    "smoke":      "smoke",
    "fire":       "smoke",
    "heat":       "heat",
    # Carbon monoxide is its own device class, and is not the same as
    # "gas", which means combustible gas.
    "co":         "carbon_monoxide",
    "carbon":     "carbon_monoxide",
    "monoxide":   "carbon_monoxide",
    "gas":        "gas",
    "propane":    "gas",
    "methane":    "gas",
    # Glass break / vibration
    "glass":      "vibration",
    "glassbreak": "vibration",
    "shock":      "vibration",
    "vibration":  "vibration",
    # Water / freeze
    "water":      "moisture",
    "leak":       "moisture",
    "flood":      "moisture",
    "moisture":   "moisture",
    "sump":       "moisture",
    "freeze":     "cold",
    "frost":      "cold",
    # Motion / occupancy
    "motion":     "motion",
    "pir":        "motion",
    "occupancy":  "occupancy",
    "presence":   "presence",
    # Doors / windows
    "garage":     "garage_door",
    "door":       "door",
    "entry":      "door",
    "entrance":   "door",
    "french":     "door",
    "patio":      "door",
    "window":     "window",
    "slider":     "window",
    "casement":   "window",
    # Tamper / panic
    "tamper":     "tamper",
    "panic":      "safety",
    "duress":     "safety",
    "holdup":     "safety",
}

_SPLIT = re.compile(r"[^a-z0-9]+")


def infer_device_class(label: str | None) -> str:
    """Return an HA BinarySensorDeviceClass string for a zone label.

    ``"opening"`` is a safe default: represents an unspecified
    open/closed contact.
    """
    if not label:
        return "opening"
    lower = label.strip().lower()

    for phrase, cls in _PHRASES:
        if phrase in lower:
            return cls

    words = [w for w in _SPLIT.split(lower) if w]
    for word in reversed(words):
        if word in _WORDS:
            return _WORDS[word]
        if word.endswith("s") and word[:-1] in _WORDS:
            return _WORDS[word[:-1]]

    return "opening"
