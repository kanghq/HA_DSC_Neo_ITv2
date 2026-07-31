"""Cached panel-configuration serialisation."""

from __future__ import annotations

import pytest

from custom_components.dsc_neo_itv2.storage import CachedPanelConfig

POPULATED = CachedPanelConfig(
    max_zones=128,
    max_partitions=8,
    max_users=95,
    zone_definitions={"1": 1, "2": 4, "3": 0},
    partition_enabled={"1": True, "2": False},
    zone_partition_assignment={"1": [1, 2], "2": [3]},
    zone_labels={"1": "Front Door", "2": "Hall Motion"},
    partition_labels={"1": "Home"},
    zone_attributes_functional={"1": 0x09},
    zone_attributes_physical={"1": 0x01},
    zone_event_reporting={"1": 0x1F},
    pgm_types={"1": 100},
    pgm_partition_assignment={"1": 1},
    fetched_at="2024-06-15T13:45:30+00:00",
)


def test_a_fresh_cache_is_empty():
    assert CachedPanelConfig().is_empty


@pytest.mark.parametrize(
    "config",
    [
        CachedPanelConfig(zone_definitions={"1": 1}),
        CachedPanelConfig(partition_enabled={"1": True}),
    ],
)
def test_a_cache_with_panel_data_is_not_empty(config):
    assert not config.is_empty


def test_labels_alone_do_not_make_a_cache_useful():
    """Without zone definitions we still need to re-read the panel."""
    assert CachedPanelConfig(zone_labels={"1": "Front Door"}).is_empty


def test_roundtrip_through_a_dict():
    assert CachedPanelConfig.from_dict(POPULATED.to_dict()) == POPULATED


def test_to_dict_is_json_serialisable():
    import json

    assert json.loads(json.dumps(POPULATED.to_dict())) == POPULATED.to_dict()


def test_from_dict_tolerates_a_completely_empty_payload():
    assert CachedPanelConfig.from_dict({}) == CachedPanelConfig()


def test_from_dict_tolerates_null_maps():
    config = CachedPanelConfig.from_dict(
        {"zone_definitions": None, "zone_labels": None, "partition_enabled": None}
    )
    assert config.zone_definitions == {}
    assert config.zone_labels == {}
    assert config.partition_enabled == {}


def test_from_dict_normalises_integer_keys_to_strings():
    config = CachedPanelConfig.from_dict({"zone_definitions": {1: 3}})
    assert config.zone_definitions == {"1": 3}


def test_from_dict_coerces_values_to_their_declared_types():
    config = CachedPanelConfig.from_dict(
        {
            "max_zones": "128",
            "zone_definitions": {"1": "4"},
            "partition_enabled": {"1": 1},
            "zone_labels": {"1": 42},
            "zone_partition_assignment": {"1": ["1", "2"]},
        }
    )
    assert config.max_zones == 128
    assert config.zone_definitions == {"1": 4}
    assert config.partition_enabled == {"1": True}
    assert config.zone_labels == {"1": "42"}
    assert config.zone_partition_assignment == {"1": [1, 2]}


@pytest.mark.parametrize(
    "field",
    [
        "zone_attributes_functional",
        "zone_attributes_physical",
        "zone_event_reporting",
        "pgm_types",
        "pgm_partition_assignment",
    ],
)
def test_byte_fields_are_masked_to_a_single_octet(field):
    config = CachedPanelConfig.from_dict({field: {"1": 0x1FF}})
    assert getattr(config, field) == {"1": 0xFF}


def test_stamp_records_an_iso_utc_timestamp():
    config = CachedPanelConfig()
    assert config.fetched_at is None
    config.stamp()
    assert config.fetched_at is not None
    assert config.fetched_at.endswith("+00:00")


def test_stamp_survives_a_roundtrip():
    config = CachedPanelConfig(zone_definitions={"1": 1})
    config.stamp()
    assert CachedPanelConfig.from_dict(config.to_dict()).fetched_at == config.fetched_at


def test_defaults_do_not_share_mutable_state():
    first = CachedPanelConfig()
    second = CachedPanelConfig()
    first.zone_labels["1"] = "Front Door"
    assert second.zone_labels == {}
