"""Architectural guard: the protocol layer must stay Home Assistant free.

``dsc_itv2/`` is a standalone, I/O-light implementation of the DSC ITv2
wire protocol. Keeping it free of ``homeassistant`` imports is what
makes the rest of this test suite runnable without a Home Assistant
install, and keeps the protocol code reusable outside HA.
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPONENT_DIR = REPO_ROOT / "custom_components" / "dsc_neo_itv2"
PROTOCOL_DIR = COMPONENT_DIR / "dsc_itv2"

PROTOCOL_MODULES = sorted(PROTOCOL_DIR.glob("*.py"))
HA_FREE_HELPERS = [
    COMPONENT_DIR / name
    for name in ("zone_definitions.py", "zone_attributes.py", "zone_labels.py")
]


def _imported_roots(path: Path) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), str(path))):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def test_the_protocol_package_exists():
    assert PROTOCOL_MODULES, f"no modules found under {PROTOCOL_DIR}"


@pytest.mark.parametrize("path", PROTOCOL_MODULES, ids=lambda p: p.name)
def test_protocol_modules_do_not_import_homeassistant(path):
    assert "homeassistant" not in _imported_roots(path)


@pytest.mark.parametrize("path", HA_FREE_HELPERS, ids=lambda p: p.name)
def test_zone_helpers_do_not_import_homeassistant(path):
    assert "homeassistant" not in _imported_roots(path)


@pytest.mark.parametrize("path", PROTOCOL_MODULES, ids=lambda p: p.name)
def test_protocol_does_not_import_the_component(path):
    """Relative imports must not escape the ``dsc_itv2`` package."""
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), str(path))):
        if isinstance(node, ast.ImportFrom):
            assert node.level <= 1, f"{path.name} imports from a parent package"


@pytest.mark.parametrize("path", PROTOCOL_MODULES, ids=lambda p: p.name)
def test_protocol_imports_are_stdlib_or_pycryptodome(path):
    """Any new third-party dependency must be added to manifest.json first."""
    allowed = {"Crypto", "dsc_itv2"} | set(sys.stdlib_module_names)
    assert _imported_roots(path) <= allowed
