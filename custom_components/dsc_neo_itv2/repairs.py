"""Repairs issue registration for actionable trouble conditions.

When the panel raises certain Trouble-group bits we surface them as
HA Repairs issues so the user gets a one-click "this needs attention"
prompt in the UI instead of having to notice a diagnostic
binary_sensor changed state.

Only actionable troubles get an issue - ones where the user can
typically do something specific:

  * **Trouble 01 - Service Required** (bell circuit, RF jam, aux supply,
    output, loss of clock)
  * **Trouble 02 - Battery** (low/missing battery)
  * **Trouble 04 - AC** (mains lost on panel/expander/siren)
  * **Trouble 11 - Communications** (TLM, FTC, cellular, ethernet)

The remaining trouble groups are still surfaced via diagnostic
binary_sensors but don't get a noisy Repairs prompt.
"""
from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Group ID -> (issue translation key, severity) for the troubles we surface
# as Repairs. Severity values: "error", "warning", "critical".
_TROUBLE_ISSUES: dict[int, tuple[str, ir.IssueSeverity]] = {
    1:  ("trouble_service_required", ir.IssueSeverity.WARNING),
    2:  ("trouble_battery",          ir.IssueSeverity.WARNING),
    4:  ("trouble_ac_loss",          ir.IssueSeverity.WARNING),
    11: ("trouble_communications",   ir.IssueSeverity.ERROR),
}


def _issue_id(entry_id: str, group_id: int) -> str:
    return f"{entry_id}_trouble_group_{group_id:02d}"


def sync_trouble_issues(
    hass: HomeAssistant,
    entry_id: str,
    active_group_ids: set[int],
) -> None:
    """Create / delete Repairs issues so the registry matches active troubles.

    For each group in :data:`_TROUBLE_ISSUES`:
      * If active and no issue exists yet, create one.
      * If not active and an issue exists, delete it.

    Idempotent and cheap to call on every trouble snapshot.
    """
    for group_id, (translation_key, severity) in _TROUBLE_ISSUES.items():
        issue_id = _issue_id(entry_id, group_id)
        if group_id in active_group_ids:
            ir.async_create_issue(
                hass=hass,
                domain=DOMAIN,
                issue_id=issue_id,
                is_fixable=False,
                severity=severity,
                translation_key=translation_key,
            )
        else:
            ir.async_delete_issue(
                hass=hass,
                domain=DOMAIN,
                issue_id=issue_id,
            )


def clear_all_trouble_issues(hass: HomeAssistant, entry_id: str) -> None:
    """Drop every trouble Repairs issue for this entry (e.g. on unload)."""
    for group_id in _TROUBLE_ISSUES:
        ir.async_delete_issue(
            hass=hass,
            domain=DOMAIN,
            issue_id=_issue_id(entry_id, group_id),
        )
    # Also drop the auth-failed marker so a fresh load starts clean.
    clear_auth_failed_issue(hass, entry_id)


# --- Auth-failure issue ----------------------------------------------------

_AUTH_ISSUE_SUFFIX = "auth_failed"


def _auth_issue_id(entry_id: str) -> str:
    return f"{entry_id}_{_AUTH_ISSUE_SUFFIX}"


def set_auth_failed_issue(
    hass: HomeAssistant, entry_id: str, reason: str | None = None,
) -> None:
    """Create a Repairs issue indicating the panel rejected our credentials.

    Triggered when the session reports a handshake failure that looks
    like an authentication problem (decryption failure on inbound
    traffic, or panel rejecting OpenSession echo / RequestAccess with
    a non-zero response code).
    """
    try:
        ir.async_create_issue(
            hass=hass,
            domain=DOMAIN,
            issue_id=_auth_issue_id(entry_id),
            is_fixable=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key="auth_failed",
            translation_placeholders={"reason": (reason or "")[:200]},
        )
    except Exception:  # pragma: no cover - defensive (e.g. test stub hass)
        _LOGGER.debug("Could not create auth_failed issue", exc_info=True)


def clear_auth_failed_issue(hass: HomeAssistant, entry_id: str) -> None:
    """Drop the auth-failed Repairs issue (e.g. on successful connect)."""
    try:
        ir.async_delete_issue(
            hass=hass,
            domain=DOMAIN,
            issue_id=_auth_issue_id(entry_id),
        )
    except Exception:  # pragma: no cover - defensive (e.g. test stub hass)
        _LOGGER.debug("Could not delete auth_failed issue", exc_info=True)


def is_auth_failure_reason(reason: str) -> bool:
    """Return True if ``reason`` looks like an authentication failure.

    These are the wording prefixes the session emits when:
      * inbound decryption fails (wrong Type-2 key)
      * the panel rejects our OpenSession echo with a non-zero code
      * the panel rejects our RequestAccess with a non-zero code

    Anything else (network error, timeout, framing error) is treated
    as a transient connection problem, not an auth problem.
    """
    if not reason:
        return False
    lowered = reason.lower()
    return (
        "decryption failed" in lowered
        or "panel rejected opensession" in lowered
        or "panel rejected our requestaccess" in lowered
    )
