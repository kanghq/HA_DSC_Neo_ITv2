"""Diagnostics export for the DSC Neo integration.

Triggered from the HA UI: Settings > Devices & Services > DSC Neo >
"..." menu > Download diagnostics.

The dump is designed for posting to bug reports. Sensitive values
(access codes, PINs, integration ID) are redacted via
``async_redact_data``. Raw protocol bytes are surfaced as hex so
maintainers can spot wire-level issues without needing a live capture.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_INSTALLER_CODE,
    CONF_INTEGRATION_ID,
    CONF_TYPE1_KEY,
    CONF_TYPE2_KEY,
    CONF_USER_PIN,
)
from .coordinator import DscNeoCoordinator
from .dsc_itv2.messages import TROUBLE_GROUP_LABELS
from .zone_attributes import (
    decode_event_reporting,
    decode_functional_attributes,
    decode_physical_attributes,
)
from .zone_definitions import (
    definition_name,
    is_24_hour_zone,
    is_fire_zone,
    is_keyswitch,
)

REDACT_KEYS = {
    CONF_INSTALLER_CODE,
    CONF_INTEGRATION_ID,
    CONF_TYPE1_KEY,
    CONF_TYPE2_KEY,
    CONF_USER_PIN,
    # Belt-and-braces: also redact anything that looks like a secret
    # the user may have put into options data under a slightly different
    # name (e.g. a future "access_code" field).
    "access_code",
    "type1_access_code",
    "type2_access_code_hex",
    "user_pin",
    "installer_code",
    "session_id",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry,
) -> dict[str, Any]:
    """Return a redacted snapshot of the coordinator + config entry state."""
    coord: DscNeoCoordinator | None = getattr(entry, "runtime_data", None)

    entry_dump = {
        "entry_id": entry.entry_id,
        "title": entry.title,
        "version": entry.version,
        "source": entry.source,
        "data": async_redact_data(dict(entry.data), REDACT_KEYS),
        "options": async_redact_data(dict(entry.options), REDACT_KEYS),
    }

    if coord is None:
        return {"entry": entry_dump, "coordinator": None}

    zones_dump = []
    for zone_no, zone in sorted(coord.zones.items()):
        definition = coord.zone_definitions.get(zone_no, 0)
        func_byte = coord.zone_attributes_functional.get(zone_no)
        phys_byte = coord.zone_attributes_physical.get(zone_no)
        report_byte = coord.zone_event_reporting.get(zone_no)
        zones_dump.append({
            "zone": zone_no,
            "label": zone.label,
            "zone_definition": definition,
            "zone_type": definition_name(definition) if definition else None,
            "is_fire_zone": is_fire_zone(definition),
            "is_24_hour_zone": is_24_hour_zone(definition),
            "is_keyswitch": is_keyswitch(definition),
            "is_open": zone.is_open,
            "is_tamper": zone.is_tamper,
            "is_trouble": zone.is_trouble,
            "is_low_battery": zone.is_low_battery,
            "is_alarm": zone.is_alarm,
            "is_bypassed": zone.is_bypassed,
            "raw_status": f"0x{zone.raw_status:02X}",
            "attributes_functional": (
                None if func_byte is None else {
                    "raw": f"0x{func_byte:02X}",
                    "flags": decode_functional_attributes(func_byte),
                }
            ),
            "attributes_physical": (
                None if phys_byte is None else {
                    "raw": f"0x{phys_byte:02X}",
                    "flags": decode_physical_attributes(phys_byte),
                }
            ),
            "event_reporting": (
                None if report_byte is None else {
                    "raw": f"0x{report_byte:02X}",
                    "flags": decode_event_reporting(report_byte),
                }
            ),
        })

    partitions_dump = []
    for part_no, part in sorted(coord.partitions.items()):
        partitions_dump.append({
            "partition": part_no,
            "label": part.label,
            "enabled": coord.partition_enabled.get(part_no),
            "assigned_zones": coord.zones_for_partition(part_no),
            "is_armed": part.is_armed,
            "arming_mode": part.arming_mode,
            "is_ready": part.is_ready,
            "is_in_alarm": part.is_in_alarm,
            "is_alarm_in_memory": part.is_alarm_in_memory,
            "is_entry_delay": part.is_entry_delay,
            "is_exit_delay": part.is_exit_delay,
            "is_trouble": part.is_trouble,
            "is_bypassed": part.is_bypassed,
            "exit_delay_seconds": part.exit_delay_seconds,
            "entry_delay_seconds": part.entry_delay_seconds,
            # last_user_id is deliberately not redacted - it's a 1-1000 numeric
            # slot, not a credential, and is useful for debugging.
            "last_user_id": part.last_user_id,
            "raw_status1": f"0x{part.raw_status1:02X}",
            "raw_status2": f"0x{part.raw_status2:02X}",
        })

    trouble_dump = {
        "any_active": coord.trouble.any_active,
        "groups": [
            {
                "group_id": gid,
                "label": TROUBLE_GROUP_LABELS.get(gid, f"Trouble {gid:02d}"),
                "bitmap": f"0x{val:02X}",
                "active": val != 0,
            }
            for gid, val in sorted(coord.trouble.groups.items())
        ],
    }

    coordinator_dump = {
        "connection_state": coord.connection_state,
        "panel_firmware": coord.panel_firmware,
        "host": coord.host,
        "port": coord.port,
        "max_zones": coord.max_zones,
        "max_partitions": coord.max_partitions,
        "max_users": coord.max_users,
        "has_panel_config": coord.has_panel_config,
        "panel_config_fetched_at": coord.panel_config_fetched_at,
        "zone_count": len(coord.zones),
        "enabled_zone_count": sum(
            1 for d in coord.zone_definitions.values() if d != 0
        ),
        "partition_count": len(coord.partitions),
        "enabled_partition_count": sum(
            1 for e in coord.partition_enabled.values() if e
        ),
        "zone_definitions": coord.zone_definitions,
        "partition_enabled": coord.partition_enabled,
        "zone_partition_assignment": coord.zone_partition_assignment,
        "zones": zones_dump,
        "partitions": partitions_dump,
        "trouble": trouble_dump,
    }
    return {
        "entry": entry_dump,
        "coordinator": async_redact_data(coordinator_dump, REDACT_KEYS),
    }
