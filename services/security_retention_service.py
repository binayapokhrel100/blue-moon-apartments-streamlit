
"""Safe security-event retention for Blue Moon Apartments."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select

from database.db import get_db_session
from database.models import (
    AuthenticationFailureAttempt,
    LoginEvent,
)


# ==========================================================
# RETENTION POLICY
# ==========================================================

DEFAULT_LOGIN_EVENT_DAYS = 180
DEFAULT_FAILURE_ATTEMPT_DAYS = 30

DEFAULT_BATCH_SIZE = 200
MAX_BATCH_SIZE = 1000


# ==========================================================
# VALIDATION AND TIME HELPERS
# ==========================================================

def _utc_naive(now: datetime | None) -> datetime:
    """Normalize dates to the application's naive UTC format."""

    if now is None:
        return datetime.now(timezone.utc).replace(
            tzinfo=None
        )

    if not isinstance(now, datetime):
        raise ValueError("A valid datetime is required.")

    if now.tzinfo is not None:
        return now.astimezone(timezone.utc).replace(
            tzinfo=None
        )

    return now


def _validate_days(
    login_days: int,
    attempt_days: int,
) -> None:
    """
    Require conservative retention periods.

    Login events must be retained for at least 90 days.
    Failure-attempt history must be retained for
    at least 1 day.
    """

    if (
        type(login_days) is not int
        or login_days < 90
    ):
        raise ValueError(
            "Login-event retention must be at least 90 days."
        )

    if (
        type(attempt_days) is not int
        or attempt_days < 1
    ):
        raise ValueError(
            "Failure-attempt retention must be at least 1 day."
        )


def _cutoffs(
    *,
    login_days: int,
    attempt_days: int,
    now: datetime | None,
) -> tuple[datetime, datetime]:
    """Return UTC retention cutoff dates."""

    _validate_days(
        login_days,
        attempt_days,
    )

    current_time = _utc_naive(now)

    return (
        current_time - timedelta(days=login_days),
        current_time - timedelta(days=attempt_days),
    )


# ==========================================================
# INTERNAL COUNT HELPERS
# ==========================================================

def _count_eligible(
    db,
    model,
    cutoff: datetime,
) -> int:
    """Count records older than their retention cutoff."""

    return int(
        db.scalar(
            select(
                func.count()
            )
            .select_from(model)
            .where(
                model.created_at < cutoff
            )
        ) or 0
    )


# ==========================================================
# READ-ONLY RETENTION PREVIEW
# ==========================================================

def preview_security_retention(
    *,
    login_days: int = DEFAULT_LOGIN_EVENT_DAYS,
    attempt_days: int = DEFAULT_FAILURE_ATTEMPT_DAYS,
    now: datetime | None = None,
) -> dict:
    """
    Preview records eligible for removal.

    No database records are deleted or modified.
    """

    login_cutoff, attempt_cutoff = _cutoffs(
        login_days=login_days,
        attempt_days=attempt_days,
        now=now,
    )

    with get_db_session() as db:

        login_count = _count_eligible(
            db,
            LoginEvent,
            login_cutoff,
        )

        failure_count = _count_eligible(
            db,
            AuthenticationFailureAttempt,
            attempt_cutoff,
        )

    return {
        "login_event_cutoff": login_cutoff,
        "failure_attempt_cutoff": attempt_cutoff,
        "eligible_login_events": login_count,
        "eligible_failure_attempts": failure_count,
    }


# ==========================================================
# EXPLICIT, BATCHED CLEANUP
# ==========================================================

def cleanup_security_retention(
    *,
    confirm: bool = False,
    login_days: int = DEFAULT_LOGIN_EVENT_DAYS,
    attempt_days: int = DEFAULT_FAILURE_ATTEMPT_DAYS,
    batch_size: int = DEFAULT_BATCH_SIZE,
    now: datetime | None = None,
) -> dict:
    """
    Remove up to batch_size expired records per table.

    Safety:
    - Requires explicit confirmation.
    - Processes bounded batches.
    - Retains recent records.
    - Does not touch administrator role-change audits.
    - Does not touch users, passwords, or reset codes.
    - Runs both deletions in one database transaction.
    """

    if confirm is not True:
        raise ValueError(
            "Explicit confirmation is required for cleanup."
        )

    if (
        type(batch_size) is not int
        or not 1 <= batch_size <= MAX_BATCH_SIZE
    ):
        raise ValueError(
            "Batch size must be between 1 and 1000."
        )

    login_cutoff, attempt_cutoff = _cutoffs(
        login_days=login_days,
        attempt_days=attempt_days,
        now=now,
    )

    with get_db_session() as db:

        # ------------------------------------------
        # SELECT EXPIRED LOGIN EVENT IDS
        # ------------------------------------------

        login_ids = list(
            db.scalars(
                select(LoginEvent.id)
                .where(
                    LoginEvent.created_at < login_cutoff
                )
                .order_by(
                    LoginEvent.created_at,
                    LoginEvent.id,
                )
                .limit(batch_size)
            ).all()
        )

        # ------------------------------------------
        # SELECT EXPIRED FAILURE ATTEMPT IDS
        # ------------------------------------------

        attempt_ids = list(
            db.scalars(
                select(AuthenticationFailureAttempt.id)
                .where(
                    AuthenticationFailureAttempt.created_at
                    < attempt_cutoff
                )
                .order_by(
                    AuthenticationFailureAttempt.created_at,
                    AuthenticationFailureAttempt.id,
                )
                .limit(batch_size)
            ).all()
        )

        # ------------------------------------------
        # DELETE ONLY SELECTED IDS
        # ------------------------------------------

        if login_ids:
            db.execute(
                delete(LoginEvent).where(
                    LoginEvent.id.in_(login_ids)
                )
            )

        if attempt_ids:
            db.execute(
                delete(AuthenticationFailureAttempt).where(
                    AuthenticationFailureAttempt.id.in_(
                        attempt_ids
                    )
                )
            )

        # ------------------------------------------
        # COUNT ANY REMAINING EXPIRED RECORDS
        # ------------------------------------------

        remaining_login = _count_eligible(
            db,
            LoginEvent,
            login_cutoff,
        )

        remaining_attempts = _count_eligible(
            db,
            AuthenticationFailureAttempt,
            attempt_cutoff,
        )

        result = {
            "deleted_login_events": len(login_ids),
            "deleted_failure_attempts": len(attempt_ids),
            "remaining_eligible_login_events": (
                remaining_login
            ),
            "remaining_eligible_failure_attempts": (
                remaining_attempts
            ),
        }

    return result
