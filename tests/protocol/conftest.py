"""Protocol-layer tests: pure functions over bytes, no Home Assistant."""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(items) -> None:
    """Tag everything in this directory with the ``protocol`` marker."""
    for item in items:
        item.add_marker(pytest.mark.protocol)
