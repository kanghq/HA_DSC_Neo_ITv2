"""Integration metadata: manifest, HACS descriptor, services and strings.

These checks are deliberately Home Assistant free so they run in the
protocol-only development loop as well as in CI.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPONENT_DIR = REPO_ROOT / "custom_components" / "dsc_neo_itv2"

MANIFEST = json.loads((COMPONENT_DIR / "manifest.json").read_text(encoding="utf-8"))
HACS = json.loads((REPO_ROOT / "hacs.json").read_text(encoding="utf-8"))
STRINGS = json.loads((COMPONENT_DIR / "strings.json").read_text(encoding="utf-8"))
EN = json.loads(
    (COMPONENT_DIR / "translations" / "en.json").read_text(encoding="utf-8")
)


# --------------------------------------------------------------------------
# manifest.json
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    [
        "domain",
        "name",
        "codeowners",
        "config_flow",
        "documentation",
        "integration_type",
        "iot_class",
        "issue_tracker",
        "requirements",
        "version",
    ],
)
def test_manifest_declares_the_required_keys(key):
    assert key in MANIFEST


def test_the_domain_matches_the_directory_name():
    assert MANIFEST["domain"] == COMPONENT_DIR.name


def test_the_integration_is_config_flow_only():
    assert MANIFEST["config_flow"] is True
    assert "config_flow.py" in {p.name for p in COMPONENT_DIR.glob("*.py")}


def test_the_integration_is_local_push():
    assert MANIFEST["iot_class"] == "local_push"


def test_the_integration_type_is_device():
    assert MANIFEST["integration_type"] == "device"


def test_the_version_is_a_three_part_number():
    parts = MANIFEST["version"].split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)


def test_doc_and_issue_urls_share_a_repository():
    documentation = MANIFEST["documentation"].rstrip("/")
    assert MANIFEST["issue_tracker"] == f"{documentation}/issues"


@pytest.mark.parametrize("key", ["documentation", "issue_tracker"])
def test_urls_are_https(key):
    assert MANIFEST[key].startswith("https://")


def test_codeowners_are_github_handles():
    assert MANIFEST["codeowners"]
    assert all(owner.startswith("@") for owner in MANIFEST["codeowners"])


def test_requirements_are_version_pinned():
    assert all(
        any(op in requirement for op in ("==", ">=", "~="))
        for requirement in MANIFEST["requirements"]
    )


def test_pycryptodome_is_declared_in_requirements():
    assert any(r.lower().startswith("pycryptodome") for r in MANIFEST["requirements"])


# --------------------------------------------------------------------------
# hacs.json
# --------------------------------------------------------------------------


def test_hacs_name_matches_the_manifest_name():
    assert HACS["name"] == MANIFEST["name"]


def test_hacs_content_is_not_in_root():
    assert HACS["content_in_root"] is False


def test_hacs_declares_a_minimum_home_assistant_version():
    parts = HACS["homeassistant"].split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)


# --------------------------------------------------------------------------
# services.yaml
# --------------------------------------------------------------------------


def test_every_service_yaml_entry_has_a_translation():
    import re

    services_yaml = (COMPONENT_DIR / "services.yaml").read_text(encoding="utf-8")
    service_names = re.findall(r"^([a-z_]+):", services_yaml, flags=re.MULTILINE)
    assert service_names
    assert set(service_names) <= set(STRINGS.get("services", {}))


# --------------------------------------------------------------------------
# strings.json / translations
# --------------------------------------------------------------------------


def test_english_translations_cover_every_string_key():
    def keys(node, prefix=""):
        if isinstance(node, dict):
            for key, value in node.items():
                yield from keys(value, f"{prefix}.{key}")
        else:
            yield prefix

    assert set(keys(STRINGS)) <= set(keys(EN))


def test_config_flow_steps_are_documented_in_strings():
    assert set(STRINGS["config"]["step"]) >= {"user", "confirm"}


def test_abort_and_error_sections_exist():
    assert STRINGS["config"]["error"]
    assert STRINGS["config"]["abort"]


# --------------------------------------------------------------------------
# Packaging hygiene
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "README.md",
        "LICENSE",
        "hacs.json",
        "custom_components/dsc_neo_itv2/manifest.json",
        "custom_components/dsc_neo_itv2/strings.json",
        "custom_components/dsc_neo_itv2/services.yaml",
        "custom_components/dsc_neo_itv2/translations/en.json",
    ],
)
def test_required_repository_files_exist(path):
    assert (REPO_ROOT / path).is_file()


def test_build_artefacts_and_secrets_are_gitignored():
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in ("__pycache__/", "*.py[cod]", "secrets.yaml", ".venv"):
        assert pattern in gitignore


def test_every_declared_platform_has_a_module():
    platforms = {
        "alarm_control_panel",
        "binary_sensor",
        "button",
        "sensor",
        "switch",
    }
    present = {p.stem for p in COMPONENT_DIR.glob("*.py")}
    assert platforms <= present


# --------------------------------------------------------------------------
# icons.json / strings.json reachability
#
# Home Assistant resolves both files by ``translation_key``. An entry whose
# key no entity sets is silently ignored: no error, no icon, no name. These
# checks exist because 15 of 26 icons.json entries were dead that way.
# --------------------------------------------------------------------------

ICONS = json.loads((COMPONENT_DIR / "icons.json").read_text(encoding="utf-8"))

PLATFORM_MODULES = (
    "alarm_control_panel",
    "binary_sensor",
    "button",
    "sensor",
    "switch",
)


def _translation_keys() -> set[tuple[str, str]]:
    """Every (platform, translation_key) an entity actually sets."""
    import ast

    found: set[tuple[str, str]] = set()
    for module in PLATFORM_MODULES:
        tree = ast.parse((COMPONENT_DIR / f"{module}.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant):
                continue
            target = node.targets[0]
            name = (
                target.id if isinstance(target, ast.Name)
                else target.attr if isinstance(target, ast.Attribute)
                else None
            )
            if name == "_attr_translation_key":
                found.add((module, node.value.value))
    return found


@pytest.mark.parametrize(
    ("platform", "key"),
    sorted((p, k) for p, entries in ICONS["entity"].items() for k in entries),
)
def test_every_icon_entry_is_reachable(platform, key):
    assert (platform, key) in _translation_keys()


@pytest.mark.parametrize(
    ("platform", "key"),
    sorted((p, k) for p, entries in STRINGS["entity"].items() for k in entries),
)
def test_every_entity_string_is_reachable(platform, key):
    assert (platform, key) in _translation_keys()


def test_entities_do_not_hardcode_icons():
    """Icons belong in icons.json; a hardcoded one shadows it."""
    for module in PLATFORM_MODULES:
        source = (COMPONENT_DIR / f"{module}.py").read_text(encoding="utf-8")
        assert "_attr_icon" not in source, f"{module}.py hardcodes an icon"
