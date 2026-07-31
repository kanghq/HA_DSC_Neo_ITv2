"""Shared pytest configuration for the DSC Neo ITv2 test suite.

Two import roots are registered:

``<repo>``
    lets Home Assistant tests import ``custom_components.dsc_neo_itv2.*``

``<repo>/custom_components/dsc_neo_itv2``
    lets the protocol tests import ``dsc_itv2.*`` directly, without
    dragging in ``custom_components/dsc_neo_itv2/__init__.py`` (which
    imports Home Assistant). This is what keeps ``tests/protocol``
    runnable with nothing but pytest and pycryptodome installed.
"""

from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPONENT_DIR = REPO_ROOT / "custom_components" / "dsc_neo_itv2"

for _path in (COMPONENT_DIR, REPO_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
