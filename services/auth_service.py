
"""Authentication services for Blue Moon Apartments."""

from datetime import datetime, timezone
from hmac import compare_digest
from typing import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from core.admin_permissions import permissions_for
from core.security import verify_password

from database.db import get_db_session

from database.models import (
    AdminCredentialState,
    AdminEmployee,
    AdminRoleAssignment,
    User,
    LoginEvent,
)

from services.auth_throttle_service import (
    acquire_authentication_lock,
    clear_failed_attempts,
    is_attempt_allowed,
    record_failed_attempt,
)


# ==========================================================
# UTC TIME HELPER
# ==========================================================

def _utc_now() -> datetime:
    """Return naive UTC matching existing database columns."""

    return datetime.now(
        timezone.utc
    ).replace(
        tzinfo=None
    )


# ==========================================================
# INTERNAL RESIDENT AUTHENTICATION
# ==========================================================

def _authenticate_user_without_throttle(
    db: Session,
    email: str,
    password: str,
) -> User | None:
    """
    Verify resident credentials inside an existing
    database transaction.

    The caller is responsible for rate limiting.
    """

    if not email or not password:
        return None

    user = db.scalar(
        select(User)
        .options(
            joinedload(User.apartment)
        )
        .where(
            func.lower(User.email) == email
        )
    )

    # ------------------------------------------
    # VERIFY ACTIVE RESIDENT ACCOUNT
    # ------------------------------------------

    if (
        user is None
        or not user.is_active
        or str(user.role or "").strip().lower() != "resident"
    ):
        return None

    # ------------------------------------------
    # VERIFY PASSWORD
    # ------------------------------------------

    if not verify_password(
        password,
        user.password_hash,
    ):
        return None

    return user


# ==========================================================
# INTERNAL ADMINISTRATOR AUTHENTICATION
# ==========================================================

def _authenticate_admin_without_throttle(
    db: Session,
    email: str,
    employee_id: str,
    password: str,
) -> User | None:
    """
    Verify administrator credentials and RBAC access.

    All database reads occur in the caller's
    existing locked transaction.
    """

    if (
        not email
        or not employee_id
        or not password
    ):
        return None

    user = db.scalar(
        select(User)
        .options(
            joinedload(User.apartment)
        )
        .where(
            func.lower(User.email) == email
        )
    )

    # ------------------------------------------
    # ACTIVE ADMINISTRATOR ACCOUNT
    # ------------------------------------------

    if (
        user is None
        or not user.is_active
        or str(user.role or "").strip().lower() != "admin"
    ):
        return None

    # ------------------------------------------
    # ACTIVE EMPLOYEE RECORD
    # ------------------------------------------

    employee = db.scalar(
        select(AdminEmployee)
        .where(
            AdminEmployee.user_id == user.id
        )
    )

    if (
        employee is None
        or not employee.is_active
    ):
        return None

    # ------------------------------------------
    # EMPLOYEE ID
    # ------------------------------------------

    stored_employee_id = (
        employee.employee_id.strip().upper()
    )

    if not compare_digest(
        stored_employee_id,
        employee_id,
    ):
        return None

    # ------------------------------------------
    # VALID RBAC ROLE
    # ------------------------------------------

    assigned_role = db.scalar(
        select(AdminRoleAssignment.role)
        .where(
            AdminRoleAssignment.user_id == user.id
        )
    )

    if not permissions_for(assigned_role):
        return None

    # ------------------------------------------
    # PENDING PASSWORD RESET
    # ------------------------------------------

    credential_state = db.get(
        AdminCredentialState,
        user.id,
    )

    if (
        credential_state is not None
        and credential_state.reset_token_hash is not None
    ):
        return None

    # ------------------------------------------
    # VERIFY PASSWORD
    # ------------------------------------------

    if not verify_password(
        password,
        user.password_hash,
    ):
        return None

    return user



# ==========================================================
# AUTHENTICATION SECURITY AUDIT
# ==========================================================

def _record_auth_security_event(
    db: Session,
    *,
    flow: str,
    email: str,
    outcome: str,
) -> None:
    """
    Record failed or blocked authentication for known
    accounts without storing submitted credentials.

    Unknown accounts remain represented only by the
    hashed identifier in the throttle table, because
    LoginEvent requires a real User foreign key.
    """

    if outcome not in {"failed", "blocked"}:
        raise ValueError(
            "Unsupported authentication audit outcome."
        )

    user_id = db.scalar(
        select(User.id).where(
            func.lower(User.email) == email
        )
    )

    if user_id is None:
        return

    db.add(
        LoginEvent(
            user_id=user_id,
            event_type=f"{flow}_{outcome}",
            success=False,
        )
    )


# ==========================================================
# ATOMIC AUTHENTICATION RATE LIMITER
# ==========================================================

def _authenticate_with_throttle(
    *,
    flow: str,
    email: str,
    authenticate: Callable[
        [Session],
        User | None,
    ],
) -> User | None:
    """
    Atomically verify authentication and record results.

    The sequence takes place in ONE transaction:

        1. Acquire SQLite write reservation.
        2. Check authentication failure limit.
        3. Verify credentials.
        4. Record failure OR clear previous failures.
        5. Commit transaction.

    SQLite serializes competing write transactions,
    preventing concurrent login attempts from all
    bypassing the same rate-limit check.
    """

    normalized_email = (
        email.strip().lower()
        if isinstance(email, str)
        else ""
    )

    if not normalized_email:
        return None

    with get_db_session() as db:

        # ------------------------------------------
        # ACQUIRE WRITE LOCK BEFORE ANY QUERY
        # ------------------------------------------

        acquire_authentication_lock(
            db
        )

        # ------------------------------------------
        # CHECK CURRENT RATE LIMIT
        # ------------------------------------------

        allowed = is_attempt_allowed(
            db,
            flow=flow,
            identifier=normalized_email,
        )

        if not allowed:
            _record_auth_security_event(
                db,
                flow=flow,
                email=normalized_email,
                outcome="blocked",
            )
            return None

        # ------------------------------------------
        # VERIFY CREDENTIALS
        # ------------------------------------------

        user = authenticate(
            db
        )

        # ------------------------------------------
        # FAILED AUTHENTICATION
        # ------------------------------------------

        if user is None:

            record_failed_attempt(
                db,
                flow=flow,
                identifier=normalized_email,
            )

            _record_auth_security_event(
                db,
                flow=flow,
                email=normalized_email,
                outcome="failed",
            )

            return None

        # ------------------------------------------
        # SUCCESSFUL AUTHENTICATION
        # ------------------------------------------

        clear_failed_attempts(
            db,
            flow=flow,
            identifier=normalized_email,
        )

        user.last_login_at = _utc_now()

        db.flush()

        return user


# ==========================================================
# PUBLIC RESIDENT AUTHENTICATION
# ==========================================================

def authenticate_user(
    email: str,
    password: str,
) -> User | None:
    """
    Authenticate residents with atomic rate limiting.

    Administrator credentials cannot authenticate
    through the resident login function.
    """

    if (
        not isinstance(email, str)
        or not isinstance(password, str)
        or not password
    ):
        return None

    normalized_email = (
        email.strip().lower()
    )

    if not normalized_email:
        return None

    return _authenticate_with_throttle(
        flow="resident_login",
        email=normalized_email,
        authenticate=lambda db: (
            _authenticate_user_without_throttle(
                db,
                normalized_email,
                password,
            )
        ),
    )


# ==========================================================
# PUBLIC ADMINISTRATOR AUTHENTICATION
# ==========================================================

def authenticate_admin(
    email: str,
    employee_id: str,
    password: str,
) -> User | None:
    """
    Authenticate administrators with atomic rate limiting.

    Preserves:
    - Employee ID validation
    - Active administrator account checks
    - RBAC role verification
    - Pending-reset restrictions
    - Bcrypt password verification
    """

    if (
        not isinstance(email, str)
        or not isinstance(employee_id, str)
        or not isinstance(password, str)
        or not password
    ):
        return None

    normalized_email = (
        email.strip().lower()
    )

    normalized_employee_id = (
        employee_id.strip().upper()
    )

    if (
        not normalized_email
        or not normalized_employee_id
    ):
        return None

    return _authenticate_with_throttle(
        flow="admin_login",
        email=normalized_email,
        authenticate=lambda db: (
            _authenticate_admin_without_throttle(
                db,
                normalized_email,
                normalized_employee_id,
                password,
            )
        ),
    )


# ==========================================================
# USER LOOKUP — EXISTING SESSION SUPPORT
# ==========================================================

def get_user_by_id(
    user_id: int,
) -> User | None:
    """Retrieve a user with apartment information."""

    with get_db_session() as db:

        return db.scalar(
            select(User)
            .options(
                joinedload(User.apartment)
            )
            .where(
                User.id == user_id
            )
        )
