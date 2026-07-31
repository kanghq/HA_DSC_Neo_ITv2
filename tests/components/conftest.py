"""Fixtures for the Home Assistant layer tests.

These tests need ``pytest-homeassistant-custom-component`` (which pulls
in Home Assistant itself). When it isn't installed: e.g. in the
protocol-only development loop: the whole directory is skipped at
collection time rather than erroring on import.
"""

from __future__ import annotations

import importlib.util
from unittest.mock import AsyncMock, MagicMock

import pytest

HA_AVAILABLE = (
    importlib.util.find_spec("pytest_homeassistant_custom_component") is not None
)

if not HA_AVAILABLE:  # pragma: no cover - environment dependent
    collect_ignore_glob = ["*.py"]
else:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.dsc_neo_itv2.const import (
        CONF_HOST,
        CONF_INSTALLER_CODE,
        CONF_INTEGRATION_ID,
        CONF_PORT,
        CONF_TYPE1_KEY,
        CONF_TYPE2_KEY,
        CONF_USER_PIN,
        DOMAIN,
    )

    ENTRY_DATA = {
        CONF_HOST: "0.0.0.0",
        CONF_PORT: 3072,
        CONF_INTEGRATION_ID: "123456789012",
        CONF_TYPE2_KEY: "00112233445566778899aabbccddeeff",
        CONF_TYPE1_KEY: "",
        CONF_USER_PIN: "1234",
        CONF_INSTALLER_CODE: "5555",
    }

    @pytest.fixture(autouse=True)
    def auto_enable_custom_integrations(enable_custom_integrations):
        """Let Home Assistant load ``custom_components/dsc_neo_itv2``."""
        yield

    @pytest.fixture
    def mock_config_entry() -> MockConfigEntry:
        return MockConfigEntry(
            domain=DOMAIN,
            title="DSC Neo (123456789012)",
            unique_id="123456789012",
            data=dict(ENTRY_DATA),
            options={},
        )

    @pytest.fixture
    def mock_coordinator() -> MagicMock:
        """A coordinator stand-in exposing the attributes consumers read."""
        coordinator = MagicMock()
        coordinator.zones = {}
        coordinator.partitions = {}
        coordinator.zone_definitions = {}
        coordinator.zone_attributes_functional = {}
        coordinator.zone_attributes_physical = {}
        coordinator.zone_event_reporting = {}
        coordinator.partition_labels = {}
        coordinator.trouble_groups = {}
        coordinator.connected = True
        coordinator.session_id = "123456789012"
        coordinator.async_request_refresh = AsyncMock()
        return coordinator


def pytest_collection_modifyitems(items):
    for item in items:
        item.add_marker(pytest.mark.ha)
