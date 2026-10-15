
"""Audited administrator login recovery for Blue Moon Apartments."""

from sqlalchemy import select

from core.admin_permissions import permissions_for

from database.db import get_db_session

from database.models import (
    AdminCredentialState,
    LoginEvent,
)

from services.admin_rbac_service import (
    _audit,
    _current_role,
    _require_active_admin,
    _require_super_admin,
)

from services.auth_throttle_service import (
    MAX_FAILURES,
    WINDOW_MINUTES,
    acquire_authentication_lock,
    clear_failed_attempts,
    get_recent_failure_count,
)


# ==========================================================
# INPUT VALIDATION
# ==========================================================

def _validate_reason(reason: str) -> str:
    """Require a meaningful recovery justification."""

    if not isinstance(reason, str):
        raise ValueError(
            "A recovery reason is required."
        )

    explanation = reason.strip()

    if not 10 <= len(explanation) <= 500:
        raise ValueError(
            "Recovery reason must contain "
            "10 to 500 characters."
        )

    return explanation


def _require_valid_target(db, target_admin_id: int):
    """
    Require an active administrator and valid RBAC role.

    Returns user, employee, role.
    """

    user, employee = _require_active_admin(
        db,
        target_admin_id,
    )

    assignment = _current_role(
        db,
        user.id,
    )

    if (
        assignment is None
        or not permissions_for(assignment.role)
    ):
        raise PermissionError(
            "Target administrator has no valid RBAC role."
        )

    return user, employee, assignment.role


# ==========================================================
# READ ADMINISTRATOR LOCKOUT STATUS
# ==========================================================

def get_admin_login_lockout_status(
    actor_id: int,
    target_admin_id: int,
) -> dict:
    """
    Return an administrator's current login status.

    Only a Super Admin can inspect this information.
    """

    with get_db_session() as db:

        _require_super_admin(
            db,
            actor_id,
        )

        user, employee, role = _require_valid_target(
            db,
            target_admin_id,
        )

        failures = get_recent_failure_count(
            db,
            flow="admin_login",
            identifier=user.email,
        )

        credential_state = db.get(
            AdminCredentialState,
            user.id,
        )

        pending_reset = bool(
            credential_state is not None
            and credential_state.reset_token_hash is not None
        )

        return {
            "user_id": user.id,
            "name": user.full_name,
            "email": user.email,
            "employee_id": employee.employee_id,
            "role": role,
            "failed_attempts": failures,
            "max_attempts": MAX_FAILURES,
            "window_minutes": WINDOW_MINUTES,
            "is_locked": failures >= MAX_FAILURES,
            "pending_password_reset": pending_reset,
        }


# ==========================================================
# SUPER ADMIN — AUDITED LOGIN UNLOCK
# ==========================================================

def unlock_admin_login(
    actor_id: int,
    target_admin_id: int,
    *,
    reason: str,
    identity_verified: bool,
) -> dict:
    """
    Clear an administrator's active login lockout.

    Security requirements:
    - Actor must be an active Super Admin.
    - Self-unlock is prohibited.
    - Target must be active with a valid role.
    - Target must have an active login lockout.
    - A pending password reset cannot be bypassed.
    - Employee identity must be verified independently.
    - A meaningful reason is mandatory.

    Only the admin_login failure counter is cleared.
    Password, employee ID, RBAC role, reset code, and
    credential version remain unchanged.

    Changes and audit records share one transaction.
    """

    explanation = _validate_reason(
        reason
    )

    if identity_verified is not True:
        raise ValueError(
            "Independent employee identity verification "
            "is required before unlocking."
        )

    with get_db_session() as db:

        # Must be the first DB operation.
        # Prevents racing an active authentication flow.

        acquire_authentication_lock(db)

        _require_super_admin(
            db,
            actor_id,
        )

        if actor_id == target_admin_id:
            raise PermissionError(
                "A Super Admin cannot unlock "
                "their own login account."
            )

        user, employee, role = _require_valid_target(
            db,
            target_admin_id,
        )

        # ------------------------------------------
        # NEVER BYPASS AN ACTIVE RESET REQUIREMENT
        # ------------------------------------------

        credential_state = db.get(
            AdminCredentialState,
            user.id,
        )

        if (
            credential_state is not None
            and credential_state.reset_token_hash is not None
        ):
            raise ValueError(
                "This administrator has a pending "
                "password reset. Complete the reset "
                "workflow instead."
            )

        # ------------------------------------------
        # VERIFY ACTIVE LOGIN LOCKOUT
        # ------------------------------------------

        failures = get_recent_failure_count(
            db,
            flow="admin_login",
            identifier=user.email,
        )

        if failures < MAX_FAILURES:
            raise ValueError(
                "This administrator does not have "
                "an active login lockout."
            )

        # ------------------------------------------
        # CLEAR ONLY ADMIN LOGIN FAILURES
        # ------------------------------------------

        clear_failed_attempts(
            db,
            flow="admin_login",
            identifier=user.email,
        )

        # ------------------------------------------
        # APPEND LOGIN SECURITY AUDIT
        # ------------------------------------------

        db.add(
            LoginEvent(
                user_id=user.id,
                event_type="admin_login_unlocked",
                success=True,
            )
        )

        # ------------------------------------------
        # APPEND SUPER ADMIN ACTION AUDIT
        # ------------------------------------------

        _audit(
            db,
            actor_id=actor_id,
            target_id=user.id,
            previous=role,
            new=role,
            action="login_unlocked",
            reason=explanation,
        )

        db.flush()

        result = {
            "user_id": user.id,
            "email": user.email,
            "employee_id": employee.employee_id,
            "unlocked": True,
            "cleared_failures": failures,
        }

    return result
