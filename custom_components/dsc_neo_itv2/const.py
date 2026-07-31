"""Constants for the DSC Neo ITv2 integration."""
from __future__ import annotations

DOMAIN = "dsc_neo_itv2"
MANUFACTURER = "DSC"
MODEL = "PowerSeries Neo (TL280/ITv2)"

# Config-entry option keys
CONF_HOST = "host"
CONF_PORT = "port"
CONF_INTEGRATION_ID = "integration_id"     # 12-digit ID from [851][422]
CONF_TYPE1_KEY = "type1_key"               # Optional: 8-digit Type-1 access code
CONF_TYPE2_KEY = "type2_key"               # 32-char hex from [851][700]
CONF_USER_PIN = "user_pin"                 # Optional stored arm/disarm code
CONF_INSTALLER_CODE = "installer_code"     # Optional, for reading panel config sections

# Defaults
DEFAULT_PORT = 3072
DEFAULT_HOST = "0.0.0.0"
DEFAULT_TYPE2_KEY = "12345678123456781234567812345678"  # DSC factory default
DEFAULT_INSTALLER_CODE = "5555"            # DSC factory default

# Dispatcher signal templates (use as f"{SIGNAL_...}_{entry_id}")
SIGNAL_ZONE_UPDATE = f"{DOMAIN}_zone_update"
SIGNAL_PARTITION_UPDATE = f"{DOMAIN}_partition_update"
SIGNAL_CONNECTION_UPDATE = f"{DOMAIN}_connection_update"
SIGNAL_NEW_ZONE = f"{DOMAIN}_new_zone"          # fires when first ZoneStatus arrives
SIGNAL_TROUBLE_UPDATE = f"{DOMAIN}_trouble_update"  # fires when system trouble bitmap changes

# HA event bus names
EVENT_ARM = f"{DOMAIN}_arm"
EVENT_DISARM = f"{DOMAIN}_disarm"
EVENT_ZONE_CHANGE = f"{DOMAIN}_zone_change"
EVENT_TROUBLE_CHANGE = f"{DOMAIN}_trouble_change"  # fires when a trouble group toggles
EVENT_PARTITION_ALARM = f"{DOMAIN}_partition_alarm"  # fires when a partition enters/exits alarm
EVENT_FIRE_PRE_ALERT = f"{DOMAIN}_fire_pre_alert"   # fires on fire-alarm verify window
EVENT_USER_ACTIVITY = f"{DOMAIN}_user_activity"     # fires on per-user keypad activity

# Connection state
CONN_STATE_DISCONNECTED = "disconnected"
CONN_STATE_HANDSHAKING = "handshaking"
CONN_STATE_CONNECTED = "connected"
CONN_STATE_FAILED = "failed"

# PGM type codes: section [009][N] returns the type byte for PGM N.
#
# Source: DSC HS2016/2032/2064/2128 installer manual,
# "[009] PGM Types" (pages 73-78 in the HS2032 EN edition). Code 100 is
# Null PGM (= unassigned). Codes for the "Zone Follower" PGM type
# (201-216, where the section maps to a block of 8 zones) are not
# enumerated here: that mode requires extra programming and we don't
# surface it as a button.
PGM_TYPE_NAMES: dict[int, str] = {
    100: "Null PGM",
    101: "Burglary and fire bell follower",
    102: "Delayed fire and burglary",
    103: "Sensor reset",
    104: "2-wire smoke",
    109: "Courtesy pulse",
    111: "Keypad buzzer follow",
    114: "Ready to arm",
    115: "System armed status",
    116: "Away armed status",
    117: "Stay armed status",
    120: "Away armed (no zones bypassed)",
    121: "Command output 1",
    122: "Command output 2",
    123: "Command output 3",
    124: "Command output 4",
    129: "Partition status / alarm memory",
    132: "Holdup output",
    134: "24-hour silent input (PGM2)",
    135: "24-hour audible input (PGM2)",
    146: "TLM and alarm",
    147: "Kissoff",
    148: "Ground start",
    149: "Alternate communicator",
    155: "System trouble",
    156: "Latched system event (strobe)",
    157: "System tamper",
    161: "DC trouble",
    165: "Proximity tag used",
    166: "Partition prox used",
    175: "Bell status / programming access",
    176: "Remote operation",
    184: "Open after alarm",
    200: "Zone follower",
}

# Map: command-output slot number (1-4, as fired by ``[*][7][N]``) ->
# the set of PGM type codes that respond to it. Output 2 is special:
# both Command Output 2 (type 122) and Sensor Reset (type 103) fire on
# ``[*][7][2]`` per the manual ("103 - Sensor Reset [*][7][2]").
COMMAND_OUTPUT_PGM_TYPES: dict[int, frozenset[int]] = {
    1: frozenset({121}),
    2: frozenset({103, 122}),
    3: frozenset({123}),
    4: frozenset({124}),
}

# Largest PGM number worth probing during the installer-mode panel-config
# pull. Onboard PGMs are 1-4; each HSM2208 8-output expander adds 8 more
# and the HSM2204 high-current module adds 4. 32 covers a fully-loaded
# HS2128 (4 onboard + up to 3x HSM2208 + HSM2204 = 32). At 50ms per
# SectionRead this adds ~3s to a panel-config reload, which only happens
# on demand. The protocol maximum is 164.
MAX_PGM_TO_PROBE = 32
