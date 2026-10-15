
"""Offline-only emergency recovery for the sole active Super Admin.

This module does not grant roles, activate accounts, or bypass
the existing one-time password-reset redemption process.

Never expose this function in Streamlit, FastAPI, or a public route.
"""

import os
import re
import secrets

from datetime import timedelta
from hashlib import sha256
from hmac import compare_digest

from sqlalchemy import func, select

from database.db import get_db_session

from database.models import (
    AdminCredentialState,
    AdminEmployee,
    AdminRoleAssignment,
    EmergencySuperAdminRecoveryEvent,
    LoginEvent,
    User,
    utc_now,
)

from services.admin_rbac_service import RESET_CODE_MINUTES

from services.auth_throttle_service import (
    acquire_authentication_lock,
    clear_failed_attempts,
)


KEY_HASH_ENV = "BM_EMERGENCY_RECOVERY_KEY_SHA256"

RECOVERY_EVENT_TYPE = "emergency_reset_code_issued"


# ==========================================================
# VALIDATION HELPERS
# ==========================================================

def _clean_text(
    value: str,
    *,
    field: str,
    minimum: int,
    maximum: int,
) -> str:
    """Reject empty, excessive, or control-character text."""

    if not isinstance(value, str):
        raise ValueError(f"Invalid {field}.")

    value = value.strip()

    if not minimum <= len(value) <= maximum:
        raise ValueError(
            f"{field} must contain "
            f"{minimum} to {maximum} characters."
        )

    if any(
        ord(character) < 32 or ord(character) == 127
        for character in value
    ):
        raise ValueError(
            f"{field} contains unsupported characters."
        )

    return value


def _verify_emergency_key(
    recovery_key: str,
) -> str:
    """Validate the separately provisioned recovery secret.

    Returns a non-secret, purpose-separated fingerprint for
    one-time-use tracking. Never log or store the raw key.
    """

    configured_hash = (
        os.environ.get(KEY_HASH_ENV, "")
        .strip()
        .lower()
    )

    if not re.fullmatch(
        r"[0-9a-f]{64}",
        configured_hash,
    ):
        raise RuntimeError(
            "Emergency recovery is not configured. "
            "Provision the recovery key securely first."
        )

    if not isinstance(recovery_key, str):
        raise PermissionError(
            "Emergency recovery authorization failed."
        )

    # Generated recovery keys are 64 characters long.
    # Reject short guesses rather than treating
    # human-chosen passwords as suitable emergency keys.
    if not 50 <= len(recovery_key) <= 256:
        raise PermissionError(
            "Emergency recovery authorization failed."
        )

    submitted_hash = sha256(
        recovery_key.encode("utf-8")
    ).hexdigest()

    if not compare_digest(
        submitted_hash,
        configured_hash,
    ):
        raise PermissionError(
            "Emergency recovery authorization failed."
        )

    # Fingerprint identifies a consumed recovery key.
    # It is different from the raw key and its verifier.
    fingerprint = sha256(
        b"blue-moon-emergency-key-use-v1:"
        + bytes.fromhex(configured_hash)
    ).hexdigest()

    return fingerprint


# ==========================================================
# ACTIVE SUPER ADMIN LOOKUP
# ==========================================================

def _active_super_admins(db):
    """Return only active users with an active employee
    record and an existing Super Admin role.
    """

    return db.execute(
        select(User, AdminEmployee)
        .join(
            AdminEmployee,
            AdminEmployee.user_id == User.id,
        )
        .join(
            AdminRoleAssignment,
            AdminRoleAssignment.user_id == User.id,
        )
        .where(
            func.lower(User.role) == "admin",
            User.is_active.is_(True),
            AdminEmployee.is_active.is_(True),
            AdminRoleAssignment.role == "super_admin",
        )
    ).all()


# ==========================================================
# READ-ONLY EMERGENCY RECOVERY PREVIEW
# ==========================================================

def preview_emergency_super_admin_recovery() -> dict:
    """Check eligibility without altering database records."""

    with get_db_session() as db:

        owners = _active_super_admins(db)

        eligible = len(owners) == 1

        if not eligible:
            return {
                "eligible": False,
                "active_super_admin_count": len(owners),
                "email": None,
                "employee_id": None,
            }

        user, employee = owners[0]

        return {
            "eligible": True,
            "active_super_admin_count": 1,
            "email": user.email,
            "employee_id": employee.employee_id,
        }


# ==========================================================
# AUDIT HELPER
# ==========================================================

def _record_recovery_event(
    db,
    *,
    user_id: int,
    fingerprint: str,
    operator_label: str,
    ticket_reference: str,
    reason: str,
    timestamp,
) -> None:
    """Record the offline action without misattributing
    it to the locked-out administrator.

    Both records are saved in the same transaction as
    the new reset code.
    """

    db.add(
        EmergencySuperAdminRecoveryEvent(
            target_user_id=user_id,
            key_fingerprint=fingerprint,
            operator_label=operator_label,
            ticket_reference=ticket_reference,
            reason=reason,
            created_at=timestamp,
        )
    )

    db.add(
        LoginEvent(
            user_id=user_id,
            event_type=RECOVERY_EVENT_TYPE,
            success=True,
        )
    )


# ==========================================================
# ISSUE EMERGENCY RESET CODE
# ==========================================================

def issue_emergency_super_admin_reset(
    *,
    email: str,
    employee_id: str,
    recovery_key: str,
    operator_label: str,
    ticket_reference: str,
    reason: str,
) -> dict:
    """Issue a one-time code to the sole active Super Admin.

    Requirements:
      - Separately stored emergency key matches.
      - That recovery key has never been used before.
      - Exactly one active Super Admin exists.
      - The selected account is that existing Super Admin.
      - The operation has an identifiable local operator.
      - An incident reference and reason are supplied.

    No role, password, or account-active flag is changed.
    """

    normalized_email = _clean_text(
        email,
        field="Email",
        minimum=3,
        maximum=255,
    ).lower()

    normalized_employee_id = _clean_text(
        employee_id,
        field="Employee ID",
        minimum=3,
        maximum=30,
    ).upper()

    operator = _clean_text(
        operator_label,
        field="Operator label",
        minimum=2,
        maximum=100,
    )

    ticket = _clean_text(
        ticket_reference,
        field="Incident reference",
        minimum=3,
        maximum=80,
    )

    explanation = _clean_text(
        reason,
        field="Recovery reason",
        minimum=10,
        maximum=300,
    )

    # Authorization must succeed before any database write.
    fingerprint = _verify_emergency_key(
        recovery_key
    )

    with get_db_session() as db:

        # First database operation. Serializes protected
        # SQLite authentication and recovery transactions.
        acquire_authentication_lock(db)

        # ----------------------------------------------
        # ENFORCE SINGLE SUPER ADMIN REQUIREMENT
        # ----------------------------------------------

        owners = _active_super_admins(db)

        if len(owners) != 1:
            raise PermissionError(
                "Emergency recovery requires exactly "
                "one active Super Admin."
            )

        user, employee = owners[0]

        if (
            user.email.strip().lower() != normalized_email
            or employee.employee_id.strip().upper()
            != normalized_employee_id
        ):
            raise PermissionError(
                "The selected account is not the "
                "sole active Super Admin."
            )

        # ----------------------------------------------
        # PROHIBIT KEY REUSE
        # ----------------------------------------------

        previously_used = db.scalar(
            select(EmergencySuperAdminRecoveryEvent.id)
            .where(
                EmergencySuperAdminRecoveryEvent
                .key_fingerprint == fingerprint
            )
            .limit(1)
        )

        if previously_used is not None:
            raise PermissionError(
                "This emergency recovery key has already "
                "been used. A new key must be provisioned."
            )

        # ----------------------------------------------
        # GENERATE STANDARD ONE-TIME RESET CODE
        # ----------------------------------------------

        raw_code = secrets.token_urlsafe(32)

        code_hash = sha256(
            raw_code.encode("utf-8")
        ).hexdigest()

        now = utc_now()

        expires_at = (
            now + timedelta(minutes=RESET_CODE_MINUTES)
        )

        # ----------------------------------------------
        # UPDATE EXISTING CREDENTIAL STATE
        # ----------------------------------------------

        state = db.get(
            AdminCredentialState,
            user.id,
        )

        if state is None:

            state = AdminCredentialState(
                user_id=user.id,
                must_change_password=True,
                credential_version=1,
                reset_token_hash=code_hash,
                reset_expires_at=expires_at,
            )

            db.add(state)

        else:

            state.must_change_password = True

            state.credential_version = (
                int(state.credential_version) + 1
            )

            state.reset_token_hash = code_hash
            state.reset_expires_at = expires_at
            state.updated_at = now

        # ----------------------------------------------
        # ALLOW STANDARD REDEMPTION OF REPLACEMENT CODE
        # ----------------------------------------------

        clear_failed_attempts(
            db,
            flow="admin_reset",
            identifier=user.email,
        )

        # The login failure counter remains unchanged.
        # Successful standard redemption clears it.

        # ----------------------------------------------
        # WRITE PERMANENT RECOVERY AUDIT
        # ----------------------------------------------

        _record_recovery_event(
            db,
            user_id=user.id,
            fingerprint=fingerprint,
            operator_label=operator,
            ticket_reference=ticket,
            reason=explanation,
            timestamp=now,
        )

        # A failed flush rolls back both the reset code
        # and the emergency key-use record.
        db.flush()

        result = {
            "user_id": user.id,
            "email": user.email,
            "employee_id": employee.employee_id,
            "reset_code": raw_code,
            "expires_at": expires_at,
        }

    # Code is returned only after commit succeeds.
    return result
