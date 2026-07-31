"""Persistent storage for per-panel config (zone defs, labels, etc.).

Stored under ``/config/.storage/dsc_neo_itv2.{entry_id}.json``. Read
once at integration setup, written after each successful
installer-mode pull. Keeps the keypad quiet during normal operation by
avoiding re-entry into installer programming mode.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import datetime as _dt
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

_STORAGE_VERSION = 1


@dataclass
class CachedPanelConfig:
    """Snapshot of installer-mode-only data captured at first install."""
    max_zones: int = 0
    max_partitions: int = 0
    max_users: int = 0
    # Map: str(zone_no) -> int (0 = NullZone = disabled)
    zone_definitions: dict[str, int] = field(default_factory=dict)
    # Map: str(partition_no) -> bool
    partition_enabled: dict[str, bool] = field(default_factory=dict)
    # Map: str(partition_no) -> list[int] of zone numbers assigned to it,
    # decoded from sections [201]..[208] (partition zone assignment bitmap).
    # When a partition is missing here we don't know which zones belong to
    # it; entities fall back to the legacy "partition 1 owns everything"
    # heuristic in that case.
    zone_partition_assignment: dict[str, list[int]] = field(default_factory=dict)
    # Map: str(zone_no) -> str
    zone_labels: dict[str, str] = field(default_factory=dict)
    # Map: str(partition_no) -> str
    partition_labels: dict[str, str] = field(default_factory=dict)
    # Map: str(zone_no) -> int: byte 0 of section [002][zone] (functional flags)
    zone_attributes_functional: dict[str, int] = field(default_factory=dict)
    # Map: str(zone_no) -> int: byte 1 of section [002][zone] (physical/loop flags)
    zone_attributes_physical: dict[str, int] = field(default_factory=dict)
    # Map: str(zone_no) -> int: section [307][zone] (event reporting flags)
    zone_event_reporting: dict[str, int] = field(default_factory=dict)
    # Map: str(pgm_no) -> int: section [009][pgm_no] (PGM type code,
    # 100 = Null PGM). Per DSC HS2xxx installer manual "[009] PGM Types".
    pgm_types: dict[str, int] = field(default_factory=dict)
    # Map: str(pgm_no) -> int: section [007][pgm_no] (PGM-to-partition
    # assignment, 1-8 or 0 if unassigned).
    pgm_partition_assignment: dict[str, int] = field(default_factory=dict)
    # ISO-8601 timestamp of the read that populated this cache
    fetched_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_zones": self.max_zones,
            "max_partitions": self.max_partitions,
            "max_users": self.max_users,
            "zone_definitions": self.zone_definitions,
            "partition_enabled": self.partition_enabled,
            "zone_partition_assignment": self.zone_partition_assignment,
            "zone_labels": self.zone_labels,
            "partition_labels": self.partition_labels,
            "zone_attributes_functional": self.zone_attributes_functional,
            "zone_attributes_physical": self.zone_attributes_physical,
            "zone_event_reporting": self.zone_event_reporting,
            "pgm_types": self.pgm_types,
            "pgm_partition_assignment": self.pgm_partition_assignment,
            "fetched_at": self.fetched_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CachedPanelConfig:
        return cls(
            max_zones=int(data.get("max_zones", 0)),
            max_partitions=int(data.get("max_partitions", 0)),
            max_users=int(data.get("max_users", 0)),
            zone_definitions={
                str(k): int(v) for k, v in (data.get("zone_definitions") or {}).items()
            },
            partition_enabled={
                str(k): bool(v) for k, v in (data.get("partition_enabled") or {}).items()
            },
            zone_partition_assignment={
                str(k): [int(z) for z in (v or [])]
                for k, v in (data.get("zone_partition_assignment") or {}).items()
            },
            zone_labels={
                str(k): str(v) for k, v in (data.get("zone_labels") or {}).items()
            },
            partition_labels={
                str(k): str(v) for k, v in (data.get("partition_labels") or {}).items()
            },
            zone_attributes_functional={
                str(k): int(v) & 0xFF
                for k, v in (data.get("zone_attributes_functional") or {}).items()
            },
            zone_attributes_physical={
                str(k): int(v) & 0xFF
                for k, v in (data.get("zone_attributes_physical") or {}).items()
            },
            zone_event_reporting={
                str(k): int(v) & 0xFF
                for k, v in (data.get("zone_event_reporting") or {}).items()
            },
            pgm_types={
                str(k): int(v) & 0xFF
                for k, v in (data.get("pgm_types") or {}).items()
            },
            pgm_partition_assignment={
                str(k): int(v) & 0xFF
                for k, v in (data.get("pgm_partition_assignment") or {}).items()
            },
            fetched_at=data.get("fetched_at"),
        )

    @property
    def is_empty(self) -> bool:
        return not (self.zone_definitions or self.partition_enabled)

    def stamp(self) -> None:
        self.fetched_at = _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds")


class PanelConfigStore:
    """Thin wrapper over HA's :class:`Store` keyed by config-entry id."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store[dict[str, Any]] = Store(
            hass, _STORAGE_VERSION, f"{DOMAIN}.{entry_id}",
        )

    async def async_load(self) -> CachedPanelConfig:
        raw = await self._store.async_load()
        if not raw:
            return CachedPanelConfig()
        try:
            return CachedPanelConfig.from_dict(raw)
        except Exception:  # pragma: no cover (corrupt store)
            _LOGGER.warning("Failed to parse cached panel config; starting fresh")
            return CachedPanelConfig()

    async def async_save(self, config: CachedPanelConfig) -> None:
        await self._store.async_save(config.to_dict())

    async def async_clear(self) -> None:
        await self._store.async_remove()
