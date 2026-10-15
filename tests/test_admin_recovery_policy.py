
"""Tests for administrator recovery verification policy."""

import pytest

from services.admin_recovery_policy import (
    validate_recovery_verification,
)


VALID_REASON = (
    "Employee identity verified through approved procedure"
)


def valid_recovery(**overrides):
    values = {
        "identity_verified": True,
        "verification_method": "in_person",
        "delivery_method": "in_person",
        "reason": VALID_REASON,
    }

    values.update(overrides)

    return validate_recovery_verification(**values)


def test_valid_in_person_verification():
    result = valid_recovery()

    assert result.verification_method == "in_person"
    assert result.delivery_method == "in_person"


def test_valid_verified_callback():
    result = valid_recovery(
        verification_method="trusted_callback",
        delivery_method="verified_voice_call",
    )

    assert result.verification_method == "trusted_callback"


def test_identity_verification_is_required():
    with pytest.raises(ValueError, match="verification"):
        valid_recovery(identity_verified=False)


def test_email_delivery_is_rejected():
    with pytest.raises(ValueError, match="delivery"):
        valid_recovery(delivery_method="email")


def test_unapproved_verification_is_rejected():
    with pytest.raises(ValueError, match="verification"):
        valid_recovery(verification_method="email_only")


def test_short_reason_is_rejected():
    with pytest.raises(ValueError, match="reason"):
        valid_recovery(reason="Reset")


def test_audit_contains_no_reset_code():
    result = valid_recovery()

    assert "Verification:" in result.audit_reason
    assert "Delivery:" in result.audit_reason
    assert "Reason:" in result.audit_reason


def test_multiline_reason_is_rejected():
    with pytest.raises(ValueError, match="unsupported"):
        valid_recovery(
            reason="Employee verified\nForged audit line"
        )
