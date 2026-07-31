"""Repairs issue helpers."""

from __future__ import annotations

import pytest

from custom_components.dsc_neo_itv2.repairs import is_auth_failure_reason


@pytest.mark.parametrize(
    "reason",
    [
        "decryption failed: MAC check failed",
        "panel rejected OpenSession echo: code=3",
        "panel rejected our RequestAccess: code=5",
    ],
)
def test_credential_errors_are_treated_as_auth_failures(reason):
    assert is_auth_failure_reason(reason)


@pytest.mark.parametrize(
    "reason",
    [
        "DECRYPTION FAILED: bad key",
        "Panel Rejected OpenSession echo: code=3",
    ],
)
def test_matching_is_case_insensitive(reason):
    assert is_auth_failure_reason(reason)


@pytest.mark.parametrize(
    "reason",
    [
        "connection reset by peer",
        "timed out waiting for the panel",
        "unexpected Connection_Poll (0x0600) in state AWAITING_OPEN_SESSION",
        "invalid 0x7E inside stuffed region",
        "CRC mismatch",
        "[Errno 98] address already in use",
    ],
)
def test_transient_errors_are_not_auth_failures(reason):
    assert not is_auth_failure_reason(reason)


@pytest.mark.parametrize("reason", ["", None])
def test_a_missing_reason_is_not_an_auth_failure(reason):
    assert not is_auth_failure_reason(reason)


def test_the_result_is_always_a_bool():
    assert is_auth_failure_reason("decryption failed") is True
    assert is_auth_failure_reason("socket closed") is False
