
"""Read-only Super Admin security monitoring for Blue Moon Apartments.

Sprint 11B.7A.

This service reads security events and current account lockout
information without changing database records.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from core.admin_permissions import permissions_for
from database.db import get_db_session

from database.models import (
    AdminEmployee,
    AdminRoleAssignment,
    AdminRoleChangeEvent,
    EmergencySuperAdminRecoveryEvent,
    LoginEvent,
    User,
)

from services.admin_rbac_service import _require_super_admin

from services.auth_throttle_service import (
    MAX_FAILURES,
    get_recent_failure_count,
)


# ==========================================================
# SECURITY AUDIT ACTIONS
# ==========================================================

SECURITY_ROLE_ACTIONS = frozenset({
    "admin_created",
    "admin_activated",
    "admin_deactivated",
    "role_assigned",
    "role_changed",
    "password_reset_requested",
    "login_unlocked",
    "bootstrap",
})


# ==========================================================
# UTC DATE NORMALIZATION
# ==========================================================

def _utc_naive(value: datetime | None) -> datetime:
    """Normalize timestamps to the application's UTC convention."""

    if value is None:
        return datetime.now(
            timezone.utc
        ).replace(tzinfo=None)

    if not isinstance(value, datetime):
        raise ValueError(
            "now must be a datetime."
        )

    if value.tzinfo is not None:
        value = value.astimezone(
            timezone.utc
        ).replace(tzinfo=None)

    return value


# ==========================================================
# SUPER ADMIN SECURITY DASHBOARD
# ==========================================================

def get_admin_security_dashboard(
    actor_id: int,
    *,
    days: int = 7,
    limit: int = 100,
    now: datetime | None = None,
) -> dict:
    """
    Return recent security activity for a verified Super Admin.

    This function:
    - Revalidates authorization inside the database session.
    - Allows a 1-to-30-day historical reporting window.
    - Limits the returned timeline to 200 events.
    - Computes metrics independently of timeline pagination.
    - Reports current administrator lockout status.
    - Does not modify database records.

    Unknown identifiers cannot be reliably associated with
    individual administrators using hashed throttle records.
    """

    # --------------------------------------------------
    # VALIDATE PARAMETERS
    # --------------------------------------------------

    if type(days) is not int or not 1 <= days <= 30:
        raise ValueError(
            "days must be an integer from 1 to 30."
        )

    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError(
            "limit must be an integer from 1 to 200."
        )

    current_time = _utc_naive(now)

    cutoff = current_time - timedelta(
        days=days
    )

    with get_db_session() as db:

        # --------------------------------------------------
        # VERIFY SUPER ADMIN
        # --------------------------------------------------

        _require_super_admin(
            db,
            actor_id,
        )

        # --------------------------------------------------
        # BASE QUERY — KNOWN ADMINISTRATOR LOGIN EVENTS
        # --------------------------------------------------

        admin_login_events = (
            select(LoginEvent.id)
            .join(
                User,
                User.id == LoginEvent.user_id,
            )
            .where(
                func.lower(User.role) == "admin",
                LoginEvent.created_at >= cutoff,
                LoginEvent.created_at <= current_time,
            )
        )

        # --------------------------------------------------
        # FAILED AUTHENTICATION EVENTS
        # --------------------------------------------------

        failed_auth_events = int(
            db.scalar(
                select(func.count())
                .select_from(
                    admin_login_events.where(
                        LoginEvent.success.is_(False)
                    ).subquery()
                )
            ) or 0
        )

        # --------------------------------------------------
        # BLOCKED AUTHENTICATION EVENTS
        # --------------------------------------------------

        blocked_auth_events = int(
            db.scalar(
                select(func.count())
                .select_from(
                    admin_login_events.where(
                        LoginEvent.event_type.like(
                            "%blocked%"
                        )
                    ).subquery()
                )
            ) or 0
        )

        # --------------------------------------------------
        # COMPLETED PASSWORD RESETS
        # --------------------------------------------------

        completed_resets = int(
            db.scalar(
                select(func.count())
                .select_from(
                    admin_login_events.where(
                        LoginEvent.event_type
                        == "password_reset_completed"
                    ).subquery()
                )
            ) or 0
        )

        # --------------------------------------------------
        # PASSWORD RESET REQUESTS
        # --------------------------------------------------

        reset_requests = int(
            db.scalar(
                select(
                    func.count(
                        AdminRoleChangeEvent.id
                    )
                )
                .where(
                    AdminRoleChangeEvent.action
                    == "password_reset_requested",
                    AdminRoleChangeEvent.created_at >= cutoff,
                    AdminRoleChangeEvent.created_at <= current_time,
                )
            ) or 0
        )

        # --------------------------------------------------
        # MANUAL ADMINISTRATOR LOGIN UNLOCKS
        # --------------------------------------------------

        manual_unlocks = int(
            db.scalar(
                select(
                    func.count(
                        AdminRoleChangeEvent.id
                    )
                )
                .where(
                    AdminRoleChangeEvent.action
                    == "login_unlocked",
                    AdminRoleChangeEvent.created_at >= cutoff,
                    AdminRoleChangeEvent.created_at <= current_time,
                )
            ) or 0
        )

        # --------------------------------------------------
        # EMERGENCY SUPER ADMIN RECOVERIES
        # --------------------------------------------------

        emergency_resets = int(
            db.scalar(
                select(
                    func.count(
                        EmergencySuperAdminRecoveryEvent.id
                    )
                )
                .where(
                    EmergencySuperAdminRecoveryEvent.created_at
                    >= cutoff,
                    EmergencySuperAdminRecoveryEvent.created_at
                    <= current_time,
                )
            ) or 0
        )

        # ==================================================
        # CURRENT ADMINISTRATOR LOCKOUT SNAPSHOT
        # ==================================================

        active_admins = db.scalars(
            select(User)
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
            )
            .order_by(User.id)
        ).all()

        account_flags = []

        for user in active_admins:

            role = db.scalar(
                select(
                    AdminRoleAssignment.role
                ).where(
                    AdminRoleAssignment.user_id
                    == user.id
                )
            )

            if not permissions_for(role):
                continue

            failure_count = get_recent_failure_count(
                db,
                flow="admin_login",
                identifier=user.email,
                now=current_time,
            )

            # Flag elevated failures before full lockout.
            if failure_count >= 3:

                account_flags.append({
                    "user_id": user.id,
                    "email": user.email,
                    "failed_attempts": failure_count,
                    "status": (
                        "Temporarily locked"
                        if failure_count >= MAX_FAILURES
                        else "Elevated failed attempts"
                    ),
                })

        account_flags.sort(
            key=lambda item: (
                -item["failed_attempts"],
                item["user_id"],
            )
        )

        locked_count = sum(
            item["failed_attempts"] >= MAX_FAILURES
            for item in account_flags
        )

        # ==================================================
        # RECENT LOGIN EVENT TIMELINE
        # ==================================================

        login_rows = db.execute(
            select(
                LoginEvent,
                User.email,
            )
            .join(
                User,
                User.id == LoginEvent.user_id,
            )
            .where(
                func.lower(User.role) == "admin",
                LoginEvent.created_at >= cutoff,
                LoginEvent.created_at <= current_time,
            )
            .order_by(
                LoginEvent.created_at.desc(),
                LoginEvent.id.desc(),
            )
            .limit(limit)
        ).all()

        # ==================================================
        # RECENT ADMINISTRATION AUDIT TIMELINE
        # ==================================================

        role_rows = db.scalars(
            select(AdminRoleChangeEvent)
            .where(
                AdminRoleChangeEvent.action.in_(
                    SECURITY_ROLE_ACTIONS
                ),
                AdminRoleChangeEvent.created_at >= cutoff,
                AdminRoleChangeEvent.created_at <= current_time,
            )
            .order_by(
                AdminRoleChangeEvent.created_at.desc(),
                AdminRoleChangeEvent.id.desc(),
            )
            .limit(limit)
        ).all()

        # ==================================================
        # RECENT EMERGENCY RECOVERY TIMELINE
        # ==================================================

        emergency_rows = db.scalars(
            select(EmergencySuperAdminRecoveryEvent)
            .where(
                EmergencySuperAdminRecoveryEvent.created_at
                >= cutoff,
                EmergencySuperAdminRecoveryEvent.created_at
                <= current_time,
            )
            .order_by(
                EmergencySuperAdminRecoveryEvent.created_at.desc(),
                EmergencySuperAdminRecoveryEvent.id.desc(),
            )
            .limit(limit)
        ).all()

        # ==================================================
        # BUILD UNIFIED TIMELINE
        # ==================================================

        timeline = []

        # Authentication events

        for event, email in login_rows:

            timeline.append({
                "time_utc": event.created_at,
                "source": "Authentication",
                "activity": event.event_type,
                "target_user_id": event.user_id,
                "actor_user_id": None,
                "account": email,
                "outcome": (
                    "Success"
                    if event.success
                    else "Failed / blocked"
                ),
                "details": "",
            })

        # Administrator audit events

        for event in role_rows:

            timeline.append({
                "time_utc": event.created_at,
                "source": "Administrator audit",
                "activity": event.action,
                "target_user_id": event.target_user_id,
                "actor_user_id": event.actor_user_id,
                "account": "",
                "outcome": "Recorded",
                "details": event.reason,
            })

        # Emergency recovery events

        for event in emergency_rows:

            timeline.append({
                "time_utc": event.created_at,
                "source": "Emergency recovery",
                "activity": "emergency_reset_code_issued",
                "target_user_id": event.target_user_id,
                "actor_user_id": None,
                "account": "",
                "outcome": "Recorded",
                "details": (
                    f"Incident {event.ticket_reference}; "
                    f"operator {event.operator_label}"
                ),
            })

        # --------------------------------------------------
        # ORDER MOST RECENT FIRST
        # --------------------------------------------------

        timeline.sort(
            key=lambda row: row["time_utc"],
            reverse=True,
        )

        # ==================================================
        # RETURN DASHBOARD SNAPSHOT
        # ==================================================

        return {
            "window_days": days,
            "generated_at_utc": current_time,
            "metrics": {
                "failed_auth_events": failed_auth_events,
                "blocked_auth_events": blocked_auth_events,
                "password_reset_requests": reset_requests,
                "completed_password_resets": completed_resets,
                "manual_unlocks": manual_unlocks,
                "emergency_resets": emergency_resets,
                "active_admin_lockouts": locked_count,
            },
            "account_flags": account_flags,
            "timeline": timeline[:limit],
        }
