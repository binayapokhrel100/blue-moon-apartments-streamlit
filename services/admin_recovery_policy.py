
"""Policy for administrator reset-code issuance and delivery."""

from dataclasses import dataclass


VERIFICATION_METHODS = {
    "in_person": "In-person identity verification",
    "trusted_callback": "Callback to previously verified contact",
}

DELIVERY_METHODS = {
    "in_person": "Delivered in person",
    "verified_voice_call": "Delivered through verified voice call",
}


@dataclass(frozen=True)
class RecoveryVerification:
    """Non-secret audit metadata, not proof of identity by itself."""

    verification_method: str
    delivery_method: str
    audit_reason: str


def validate_recovery_verification(
    *,
    identity_verified: bool,
    verification_method: str,
    delivery_method: str,
    reason: str,
) -> RecoveryVerification:
    """Require approved identity verification and delivery procedures."""

    if identity_verified is not True:
        raise ValueError(
            "Independent employee identity verification "
            "must be completed before issuing a reset code."
        )

    if verification_method not in VERIFICATION_METHODS:
        raise ValueError(
            "Select an approved identity verification method."
        )

    if delivery_method not in DELIVERY_METHODS:
        raise ValueError(
            "Select an approved reset-code delivery method."
        )

    if not isinstance(reason, str):
        raise ValueError("A recovery reason is required.")

    cleaned_reason = reason.strip()

    if not 10 <= len(cleaned_reason) <= 300:
        raise ValueError(
            "Recovery reason must contain 10 to 300 characters."
        )

    if any(
        ord(char) < 32 or ord(char) == 127
        for char in cleaned_reason
    ):
        raise ValueError(
            "Recovery reason contains unsupported characters."
        )

    audit_reason = (
        f"Verification: {VERIFICATION_METHODS[verification_method]}; "
        f"Delivery: {DELIVERY_METHODS[delivery_method]}; "
        f"Reason: {cleaned_reason}"
    )

    return RecoveryVerification(
        verification_method=verification_method,
        delivery_method=delivery_method,
        audit_reason=audit_reason,
    )
