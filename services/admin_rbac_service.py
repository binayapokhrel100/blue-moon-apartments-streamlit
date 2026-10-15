
"""Blue Moon Apartments — administrator role management and security."""

import re
import secrets

from datetime import timedelta
from hashlib import sha256
from hmac import compare_digest

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from core.admin_permissions import (
    ROLE_LABELS,
    ROLES,
    permissions_for,
    valid_role,
)
from core.security import hash_password, verify_password
from database.db import get_db_session
from database.models import (
    AdminEmployee,
    AdminCredentialState,
    AdminRoleAssignment,
    AdminRoleChangeEvent,
    LoginEvent,
    User,
    utc_now,
)
from services.admin_recovery_policy import validate_recovery_verification
from services.auth_throttle_service import (
    acquire_authentication_lock,
    is_attempt_allowed,
    record_failed_attempt,
    clear_failed_attempts,
)


# ==========================================================
# ADMINISTRATOR ACCESS HELPERS
# ==========================================================

def _require_active_admin(
    db,
    user_id: int,
) -> tuple[User, AdminEmployee]:

    user = db.scalar(
        select(User).where(
            User.id == user_id,
            func.lower(User.role) == "admin",
            User.is_active.is_(True),
        )
    )

    if user is None:
        raise PermissionError(
            "Active administrator account required."
        )

    employee = db.scalar(
        select(AdminEmployee).where(
            AdminEmployee.user_id == user_id,
            AdminEmployee.is_active.is_(True),
        )
    )

    if employee is None:
        raise PermissionError(
            "Active administrator employee record required."
        )

    return user, employee


def _current_role(
    db,
    user_id: int,
) -> AdminRoleAssignment | None:

    return db.scalar(
        select(AdminRoleAssignment).where(
            AdminRoleAssignment.user_id == user_id
        )
    )


def _require_super_admin(
    db,
    actor_id: int,
) -> None:

    _require_active_admin(db, actor_id)

    assignment = _current_role(db, actor_id)

    if (
        assignment is None
        or assignment.role != "super_admin"
    ):
        raise PermissionError(
            "Super Admin privileges required."
        )


def _audit(
    db,
    *,
    actor_id: int,
    target_id: int,
    previous: str | None,
    new: str,
    action: str,
    reason: str,
) -> None:

    db.add(
        AdminRoleChangeEvent(
            actor_user_id=actor_id,
            target_user_id=target_id,
            previous_role=previous,
            new_role=new,
            action=action,
            reason=reason,
        )
    )


# ==========================================================
# TRUSTED SUPER ADMIN BOOTSTRAP
# ==========================================================

def bootstrap_initial_super_admin(email: str) -> int:
    """One-time bootstrap of the first Super Admin.

    Safeguards:
    - Requires an existing, active administrator.
    - Requires an active employee record.
    - Refuses when any Super Admin assignment exists.
    - Refuses when a previous bootstrap audit exists.
    - Uses the existing SQLite authentication lock.
    - Never creates a user or modifies a password.
    - Records the initial assignment atomically.

    Trusted provisioning CLI only.
    Do not expose through Streamlit or public APIs.
    """

    normalized_email = (
        email or ""
    ).strip().lower()

    if (
        not normalized_email
        or "@" not in normalized_email
    ):
        raise ValueError(
            "Provide the existing administrator email."
        )

    with get_db_session() as db:

        # Must occur before any other database query.
        acquire_authentication_lock(db)

        # ------------------------------------------
        # CHECK HISTORICAL BOOTSTRAP
        # ------------------------------------------

        previous_bootstrap = db.scalar(
            select(AdminRoleChangeEvent.id)
            .where(
                AdminRoleChangeEvent.action == "bootstrap"
            )
            .limit(1)
        )

        if previous_bootstrap is not None:
            raise ValueError(
                "Super Admin bootstrap has already "
                "been performed. Re-bootstrap is disabled."
            )

        # ------------------------------------------
        # CHECK EXISTING SUPER ADMIN ROLE
        # ------------------------------------------

        existing_owner = db.scalar(
            select(AdminRoleAssignment.user_id)
            .where(
                AdminRoleAssignment.role == "super_admin"
            )
            .limit(1)
        )

        if existing_owner is not None:
            raise ValueError(
                "A Super Admin assignment already exists; "
                "bootstrap is disabled."
            )

        # ------------------------------------------
        # FIND EXISTING ADMINISTRATOR
        # ------------------------------------------

        user = db.scalar(
            select(User).where(
                func.lower(User.email)
                == normalized_email
            )
        )

        if user is None:
            raise ValueError(
                "No matching administrator account found."
            )

        _require_active_admin(
            db,
            user.id,
        )

        # ------------------------------------------
        # PREVENT ROLE REPLACEMENT
        # ------------------------------------------

        if _current_role(db, user.id) is not None:
            raise ValueError(
                "This administrator already has "
                "a role assignment."
            )

        # ------------------------------------------
        # CREATE INITIAL ROLE ASSIGNMENT
        # ------------------------------------------

        db.add(
            AdminRoleAssignment(
                user_id=user.id,
                role="super_admin",
                assigned_by=user.id,
            )
        )

        # ------------------------------------------
        # RECORD PERMANENT BOOTSTRAP AUDIT
        # ------------------------------------------

        _audit(
            db,
            actor_id=user.id,
            target_id=user.id,
            previous=None,
            new="super_admin",
            action="bootstrap",
            reason=(
                "One-time local Super Admin provisioning"
            ),
        )

        db.flush()

        return user.id


# ==========================================================
# CURRENT ADMINISTRATOR ACCESS
# ==========================================================

def get_my_admin_access(
    admin_id: int,
) -> dict:

    with get_db_session() as db:

        user, employee = _require_active_admin(
            db,
            admin_id,
        )

        assignment = _current_role(
            db,
            admin_id,
        )

        role = (
            assignment.role
            if assignment is not None
            else None
        )

        credential = db.get(
            AdminCredentialState,
            admin_id,
        )

        return {
            "user_id": user.id,
            "email": user.email,
            "employee_id": employee.employee_id,
            "role": role,
            "role_label": ROLE_LABELS.get(
                role,
                "Unassigned",
            ),
            "permissions": sorted(
                permissions_for(role)
            ),
            "must_change_password": (
                bool(credential.must_change_password)
                if credential is not None
                else False
            ),
            "credential_version": (
                int(credential.credential_version)
                if credential is not None
                else 0
            ),
        }


# ==========================================================
# ADMINISTRATOR DIRECTORY
# ==========================================================

def list_admin_role_assignments(
    actor_id: int,
) -> list[dict]:

    with get_db_session() as db:

        _require_super_admin(db, actor_id)

        result = db.execute(
            select(
                User,
                AdminEmployee,
                AdminRoleAssignment,
            )
            .join(
                AdminEmployee,
                AdminEmployee.user_id == User.id,
            )
            .outerjoin(
                AdminRoleAssignment,
                AdminRoleAssignment.user_id == User.id,
            )
            .where(
                func.lower(User.role) == "admin"
            )
            .order_by(
                User.last_name,
                User.first_name,
                User.id,
            )
        ).all()

        return [
            {
                "user_id": user.id,
                "name": user.full_name,
                "email": user.email,
                "employee_id": employee.employee_id,
                "active": bool(
                    user.is_active
                    and employee.is_active
                ),
                "role": (
                    assignment.role
                    if assignment is not None
                    else None
                ),
                "role_label": ROLE_LABELS.get(
                    assignment.role
                    if assignment is not None
                    else None,
                    "Unassigned",
                ),
            }
            for user, employee, assignment in result
        ]


# ==========================================================
# ASSIGN OR CHANGE ADMINISTRATOR ROLE
# ==========================================================

def assign_admin_role(
    actor_id: int,
    target_admin_id: int,
    new_role: str,
    *,
    reason: str,
) -> None:

    if not valid_role(new_role):
        raise ValueError(
            "Invalid administrator role."
        )

    cleaned_reason = (reason or "").strip()

    if not 10 <= len(cleaned_reason) <= 500:
        raise ValueError(
            "Role-change reason must be 10–500 characters."
        )

    with get_db_session() as db:

        _require_super_admin(db, actor_id)
        _require_active_admin(db, target_admin_id)

        if actor_id == target_admin_id:
            raise ValueError(
                "Administrators cannot change their own role."
            )

        prior = _current_role(
            db,
            target_admin_id,
        )

        old_role = (
            prior.role
            if prior is not None
            else None
        )

        if old_role == new_role:
            raise ValueError(
                "Administrator already has this role."
            )

        if old_role == "super_admin":

            active_owners = db.scalar(
                select(func.count(AdminRoleAssignment.id))
                .join(
                    User,
                    User.id == AdminRoleAssignment.user_id,
                )
                .join(
                    AdminEmployee,
                    AdminEmployee.user_id == User.id,
                )
                .where(
                    AdminRoleAssignment.role == "super_admin",
                    User.is_active.is_(True),
                    AdminEmployee.is_active.is_(True),
                )
            ) or 0

            if active_owners <= 1:
                raise ValueError(
                    "Cannot demote the last active Super Admin."
                )

        if prior is None:

            db.add(
                AdminRoleAssignment(
                    user_id=target_admin_id,
                    role=new_role,
                    assigned_by=actor_id,
                )
            )

        else:

            result = db.execute(
                update(AdminRoleAssignment)
                .where(
                    AdminRoleAssignment.id == prior.id,
                    AdminRoleAssignment.role == old_role,
                )
                .values(
                    role=new_role,
                    assigned_by=actor_id,
                    updated_at=utc_now(),
                )
            )

            if result.rowcount != 1:
                raise ValueError(
                    "Role changed concurrently. Refresh and retry."
                )

        _audit(
            db,
            actor_id=actor_id,
            target_id=target_admin_id,
            previous=old_role,
            new=new_role,
            action=(
                "role_assigned"
                if old_role is None
                else "role_changed"
            ),
            reason=cleaned_reason,
        )

        db.flush()


# ==========================================================
# ROLE AND ACCOUNT AUDIT HISTORY
# ==========================================================

def list_admin_role_audit(
    actor_id: int,
    limit: int = 100,
) -> list[dict]:

    with get_db_session() as db:

        _require_super_admin(db, actor_id)

        events = db.scalars(
            select(AdminRoleChangeEvent)
            .order_by(
                AdminRoleChangeEvent.id.desc()
            )
            .limit(
                max(1, min(limit, 500))
            )
        ).all()

        return [
            {
                "timestamp": event.created_at,
                "actor_user_id": event.actor_user_id,
                "target_user_id": event.target_user_id,
                "previous_role": event.previous_role,
                "new_role": event.new_role,
                "action": event.action,
                "reason": event.reason,
            }
            for event in events
        ]


# ==========================================================
# CREATE ADMINISTRATOR EMPLOYEE
# ==========================================================

def create_admin_employee(
    actor_id: int,
    *,
    first_name: str,
    last_name: str,
    email: str,
    employee_id: str,
    password: str,
    role: str,
    reason: str,
) -> int:

    first = (first_name or "").strip()
    last = (last_name or "").strip()
    mail = (email or "").strip().lower()
    employee_code = (employee_id or "").strip().upper()
    explanation = (reason or "").strip()

    if (
        not first
        or not last
        or len(first) > 100
        or len(last) > 100
    ):
        raise ValueError(
            "First and last names are required "
            "(up to 100 characters each)."
        )

    if (
        len(mail) > 255
        or not re.fullmatch(
            r"[^@\s]+@[^@\s]+\.[^@\s]+",
            mail,
        )
    ):
        raise ValueError(
            "Enter a valid administrator email address."
        )

    if not re.fullmatch(
        r"[A-Z0-9][A-Z0-9-]{2,29}",
        employee_code,
    ):
        raise ValueError(
            "Employee ID must be 3–30 letters, "
            "digits, or hyphens."
        )

    if not valid_role(role):
        raise ValueError(
            "Invalid administrator role."
        )

    if not 10 <= len(explanation) <= 500:
        raise ValueError(
            "Account creation reason must be 10–500 characters."
        )

    if (
        not isinstance(password, str)
        or not 12 <= len(password.encode("utf-8")) <= 72
    ):
        raise ValueError(
            "Password must contain 12–72 UTF-8 bytes."
        )

    try:
        with get_db_session() as db:

            _require_super_admin(
                db,
                actor_id,
            )

            if db.scalar(
                select(User.id).where(
                    func.lower(User.email) == mail
                )
            ) is not None:
                raise ValueError(
                    "That email address is already registered."
                )

            if db.scalar(
                select(AdminEmployee.id).where(
                    func.lower(AdminEmployee.employee_id)
                    == employee_code.lower()
                )
            ) is not None:
                raise ValueError(
                    "That employee ID already exists."
                )

            account = User(
                first_name=first,
                last_name=last,
                email=mail,
                password_hash=hash_password(password),
                role="admin",
                is_active=True,
                apartment_id=None,
            )

            db.add(account)
            db.flush()

            db.add(
                AdminEmployee(
                    user_id=account.id,
                    employee_id=employee_code,
                    is_active=True,
                )
            )

            db.add(
                AdminRoleAssignment(
                    user_id=account.id,
                    role=role,
                    assigned_by=actor_id,
                )
            )

            db.add(
                AdminCredentialState(
                    user_id=account.id,
                    must_change_password=True,
                    credential_version=0,
                )
            )

            _audit(
                db,
                actor_id=actor_id,
                target_id=account.id,
                previous=None,
                new=role,
                action="admin_created",
                reason=explanation,
            )

            db.flush()
            return account.id

    except IntegrityError as exc:
        raise ValueError(
            "An email address or employee ID is already "
            "registered. Refresh and try again."
        ) from exc


# ==========================================================
# ACTIVATE / DEACTIVATE ADMINISTRATOR
# ==========================================================

def set_admin_employee_active(
    actor_id: int,
    target_admin_id: int,
    *,
    active: bool,
    reason: str,
) -> None:

    if type(active) is not bool:
        raise ValueError(
            "Account status must be True or False."
        )

    cleaned_reason = (reason or "").strip()

    if not 10 <= len(cleaned_reason) <= 500:
        raise ValueError(
            "Status-change reason must contain "
            "10–500 characters."
        )

    with get_db_session() as db:

        _require_super_admin(db, actor_id)

        if actor_id == target_admin_id:
            raise ValueError(
                "Administrators cannot change "
                "their own account status."
            )

        user = db.scalar(
            select(User).where(
                User.id == target_admin_id,
                func.lower(User.role) == "admin",
            )
        )

        if user is None:
            raise ValueError(
                "Administrator account not found."
            )

        employee = db.scalar(
            select(AdminEmployee).where(
                AdminEmployee.user_id == target_admin_id
            )
        )

        if employee is None:
            raise ValueError(
                "Administrator employee record not found."
            )

        user_active = bool(user.is_active)
        employee_active = bool(employee.is_active)

        if user_active != employee_active:
            raise ValueError(
                "Administrator account and employee "
                "statuses are inconsistent. "
                "Review the database before continuing."
            )

        if user_active == active:
            raise ValueError(
                "Administrator account is already "
                + ("active." if active else "inactive.")
            )

        assignment = _current_role(
            db,
            target_admin_id,
        )

        role = (
            assignment.role
            if assignment is not None
            else None
        )

        # Prevent deactivating the last active Super Admin.

        if not active and role == "super_admin":

            active_owners = db.scalar(
                select(func.count(AdminRoleAssignment.id))
                .join(
                    User,
                    User.id == AdminRoleAssignment.user_id,
                )
                .join(
                    AdminEmployee,
                    AdminEmployee.user_id == User.id,
                )
                .where(
                    AdminRoleAssignment.role == "super_admin",
                    User.is_active.is_(True),
                    AdminEmployee.is_active.is_(True),
                )
            ) or 0

            if active_owners <= 1:
                raise ValueError(
                    "Cannot deactivate the last active Super Admin."
                )

        user_result = db.execute(
            update(User)
            .where(
                User.id == target_admin_id,
                User.is_active.is_(user_active),
            )
            .values(
                is_active=active
            )
        )

        if user_result.rowcount != 1:
            raise ValueError(
                "Account status changed concurrently. "
                "Refresh and retry."
            )

        employee_result = db.execute(
            update(AdminEmployee)
            .where(
                AdminEmployee.user_id == target_admin_id,
                AdminEmployee.is_active.is_(employee_active),
            )
            .values(
                is_active=active
            )
        )

        if employee_result.rowcount != 1:
            raise ValueError(
                "Employee status changed concurrently. "
                "Refresh and retry."
            )

        _audit(
            db,
            actor_id=actor_id,
            target_id=target_admin_id,
            previous=role,
            new=role or "unassigned",
            action=(
                "admin_activated"
                if active
                else "admin_deactivated"
            ),
            reason=cleaned_reason,
        )

        db.flush()


# ==========================================================
# ADMINISTRATOR PASSWORD POLICY
# ==========================================================

def _validate_new_admin_password(
    password: str,
) -> None:

    if not isinstance(password, str):
        raise ValueError(
            "Enter a valid new password."
        )

    length = len(password.encode("utf-8"))

    if not 12 <= length <= 72:
        raise ValueError(
            "Password must contain 12–72 UTF-8 bytes."
        )

    if not (
        any(char.isupper() for char in password)
        and any(char.islower() for char in password)
        and any(char.isdigit() for char in password)
        and any(not char.isalnum() for char in password)
    ):
        raise ValueError(
            "Password must include uppercase and "
            "lowercase letters, a number, and a "
            "special character."
        )


# ==========================================================
# CHANGE OWN ADMINISTRATOR PASSWORD
# ==========================================================

def change_own_admin_password(
    admin_id: int,
    *,
    current_password: str,
    new_password: str,
    confirm_password: str,
) -> None:

    if new_password != confirm_password:
        raise ValueError(
            "New password and confirmation do not match."
        )

    _validate_new_admin_password(new_password)

    with get_db_session() as db:

        acquire_authentication_lock(db)

        user, _ = _require_active_admin(
            db,
            admin_id,
        )

        assignment = _current_role(
            db,
            admin_id,
        )

        if (
            assignment is None
            or not permissions_for(assignment.role)
        ):
            raise PermissionError(
                "A valid administrator role is required."
            )

        if not verify_password(
            current_password,
            user.password_hash,
        ):
            raise ValueError(
                "Current password is incorrect."
            )

        if verify_password(
            new_password,
            user.password_hash,
        ):
            raise ValueError(
                "Your new password must differ "
                "from the current password."
            )

        previous_hash = user.password_hash

        result = db.execute(
            update(User)
            .where(
                User.id == admin_id,
                User.password_hash == previous_hash,
                User.is_active.is_(True),
            )
            .values(
                password_hash=hash_password(new_password)
            )
        )

        if result.rowcount != 1:
            raise ValueError(
                "Password changed concurrently. "
                "Please sign in again."
            )

        state = db.get(
            AdminCredentialState,
            admin_id,
        )

        if state is None:
            state = AdminCredentialState(
                user_id=admin_id,
                must_change_password=False,
                credential_version=0,
            )
            db.add(state)

        state.must_change_password = False
        state.credential_version = (
            int(state.credential_version) + 1
        )
        state.reset_token_hash = None
        state.reset_expires_at = None

        db.add(
            LoginEvent(
                user_id=admin_id,
                event_type="password_changed",
                success=True,
            )
        )

        db.flush()


# ==========================================================
# PASSWORD RESET CONSTANTS
# ==========================================================

RESET_CODE_MINUTES = 15
INVALID_RESET_MESSAGE = "Invalid or expired reset code."


# ==========================================================
# ISSUE ADMINISTRATOR RESET CODE — SPRINT 11B.6C
# ==========================================================

def request_admin_password_reset(
    actor_id: int,
    target_admin_id: int,
    *,
    reason: str,
    identity_verified: bool = False,
    verification_method: str = "",
    delivery_method: str = "",
) -> str:
    """
    Issue a one-time reset code only after documented
    identity verification.

    The code is returned to the caller exactly once.
    Only its SHA-256 hash is stored.
    """

    with get_db_session() as db:

        acquire_authentication_lock(db)

        _require_super_admin(db, actor_id)

        if actor_id == target_admin_id:
            raise ValueError(
                "Use My Account to change your own password."
            )

        user, _ = _require_active_admin(
            db,
            target_admin_id,
        )

        assignment = _current_role(
            db,
            target_admin_id,
        )

        if (
            assignment is None
            or not permissions_for(assignment.role)
        ):
            raise ValueError(
                "The administrator has no valid assigned role."
            )

        # Enforce policy at the backend, not only in UI.

        verification = validate_recovery_verification(
            identity_verified=identity_verified,
            verification_method=verification_method,
            delivery_method=delivery_method,
            reason=reason,
        )

        raw_code = secrets.token_urlsafe(32)

        code_hash = sha256(
            raw_code.encode("utf-8")
        ).hexdigest()

        expires_at = utc_now() + timedelta(
            minutes=RESET_CODE_MINUTES
        )

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
            state.updated_at = utc_now()

        # Record approved verification details, never the code.

        _audit(
            db,
            actor_id=actor_id,
            target_id=user.id,
            previous=assignment.role,
            new=assignment.role,
            action="password_reset_requested",
            reason=verification.audit_reason,
        )

        # A replacement code resets earlier failed
        # redemption attempts.

        clear_failed_attempts(
            db,
            flow="admin_reset",
            identifier=user.email,
        )

        db.flush()
        return raw_code


# ==========================================================
# REDEEM PASSWORD RESET CODE — ATOMIC TRANSACTION
# ==========================================================

def redeem_admin_password_reset(
    *,
    email: str,
    employee_id: str,
    reset_code: str,
    new_password: str,
    confirm_password: str,
) -> None:
    """
    Validate and consume a reset code within one
    SQLite transaction.

    Invalid attempts are recorded before committing.
    """

    if new_password != confirm_password:
        raise ValueError(
            "New password and confirmation do not match."
        )

    _validate_new_admin_password(new_password)

    normalized_email = (
        email.strip().lower()
        if isinstance(email, str)
        else ""
    )

    normalized_employee_id = (
        employee_id.strip().upper()
        if isinstance(employee_id, str)
        else ""
    )

    code = (
        reset_code.strip()
        if isinstance(reset_code, str)
        else ""
    )

    if (
        not normalized_email
        or len(normalized_email) > 320
        or not normalized_employee_id
        or not code
        or len(code) > 256
    ):
        raise ValueError(INVALID_RESET_MESSAGE)

    submitted_hash = sha256(
        code.encode("utf-8")
    ).hexdigest()

    failure_message = None

    with get_db_session() as db:

        acquire_authentication_lock(db)

        now = utc_now()

        user = db.scalar(
            select(User).where(
                func.lower(User.email) == normalized_email,
                func.lower(User.role) == "admin",
            )
        )

        allowed = is_attempt_allowed(
            db,
            flow="admin_reset",
            identifier=normalized_email,
            now=now,
        )

        if not allowed:

            if user is not None:
                db.add(
                    LoginEvent(
                        user_id=user.id,
                        event_type="admin_reset_blocked",
                        success=False,
                    )
                )

            failure_message = INVALID_RESET_MESSAGE

        else:

            employee = None
            assignment = None
            state = None

            if user is not None:

                employee = db.scalar(
                    select(AdminEmployee).where(
                        AdminEmployee.user_id == user.id
                    )
                )

                assignment = _current_role(
                    db,
                    user.id,
                )

                state = db.get(
                    AdminCredentialState,
                    user.id,
                )

            employee_matches = bool(
                employee is not None
                and employee.is_active
                and compare_digest(
                    employee.employee_id.strip().upper(),
                    normalized_employee_id,
                )
            )

            role_is_valid = bool(
                assignment is not None
                and permissions_for(assignment.role)
            )

            stored_hash = (
                state.reset_token_hash
                if state is not None
                and state.reset_token_hash
                else "0" * 64
            )

            code_matches = compare_digest(
                stored_hash,
                submitted_hash,
            )

            code_not_expired = bool(
                state is not None
                and state.reset_expires_at is not None
                and state.reset_expires_at > now
            )

            valid_reset = bool(
                user is not None
                and user.is_active
                and employee_matches
                and role_is_valid
                and code_matches
                and code_not_expired
            )

            if not valid_reset:

                record_failed_attempt(
                    db,
                    flow="admin_reset",
                    identifier=normalized_email,
                    now=now,
                )

                if user is not None:
                    db.add(
                        LoginEvent(
                            user_id=user.id,
                            event_type="admin_reset_failed",
                            success=False,
                        )
                    )

                failure_message = INVALID_RESET_MESSAGE

            else:

                if verify_password(
                    new_password,
                    user.password_hash,
                ):
                    raise ValueError(
                        "New password must differ from "
                        "the previous password."
                    )

                previous_hash = user.password_hash
                previous_version = int(
                    state.credential_version
                )

                password_result = db.execute(
                    update(User)
                    .where(
                        User.id == user.id,
                        User.is_active.is_(True),
                        User.password_hash == previous_hash,
                    )
                    .values(
                        password_hash=hash_password(new_password)
                    )
                )

                if password_result.rowcount != 1:
                    raise ValueError(
                        "Password changed concurrently. "
                        "Request a new reset code."
                    )

                code_result = db.execute(
                    update(AdminCredentialState)
                    .where(
                        AdminCredentialState.user_id == user.id,
                        AdminCredentialState.reset_token_hash
                        == submitted_hash,
                        AdminCredentialState.reset_expires_at > now,
                        AdminCredentialState.credential_version
                        == previous_version,
                    )
                    .values(
                        reset_token_hash=None,
                        reset_expires_at=None,
                        must_change_password=False,
                        credential_version=previous_version + 1,
                        updated_at=now,
                    )
                )

                if code_result.rowcount != 1:
                    raise ValueError(INVALID_RESET_MESSAGE)

                clear_failed_attempts(
                    db,
                    flow="admin_reset",
                    identifier=normalized_email,
                )

                clear_failed_attempts(
                    db,
                    flow="admin_login",
                    identifier=normalized_email,
                )

                db.add(
                    LoginEvent(
                        user_id=user.id,
                        event_type="password_reset_completed",
                        success=True,
                    )
                )

        db.flush()

    # Invalid attempts must commit before raising.
    # Raising within the session would roll back
    # their failure counters and audit events.

    if failure_message:
        raise ValueError(failure_message)
