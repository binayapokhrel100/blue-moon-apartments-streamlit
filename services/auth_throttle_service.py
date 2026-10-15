
"""Authentication rate limiting for Blue Moon Apartments."""

from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from hashlib import sha256

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from database.models import AuthenticationFailureAttempt


# ==========================================================
# RATE LIMIT POLICY
# ==========================================================

MAX_FAILURES = 5
WINDOW_MINUTES = 15

SUPPORTED_FLOWS = frozenset({
    "admin_login",
    "resident_login",
    "admin_reset",
})


# ==========================================================
# HELPERS
# ==========================================================

def _utc_now() -> datetime:
    """Return naive UTC time for database compatibility."""

    return datetime.now(timezone.utc).replace(tzinfo=None)


def _fingerprint(
    flow: str,
    identifier: str,
) -> str | None:
    """
    Derive a consistent lookup key.

    Do not store the raw email in the attempt table.
    The flow prefix keeps independent rate limits
    for login and password-reset operations.
    """

    if flow not in SUPPORTED_FLOWS:
        raise ValueError(
            "Unsupported authentication flow."
        )

    if not isinstance(identifier, str):
        return None

    normalized = identifier.strip().casefold()

    if not normalized or len(normalized) > 320:
        return None

    payload = f"{flow}\\x00{normalized}"

    return sha256(
        payload.encode("utf-8")
    ).hexdigest()


# ==========================================================
# CHECK WHETHER AN ATTEMPT IS ALLOWED
# ==========================================================

def is_attempt_allowed(
    db: Session,
    *,
    flow: str,
    identifier: str,
    now: datetime | None = None,
) -> bool:
    """Reject identities with too many recent failures."""

    identity_hash = _fingerprint(
        flow,
        identifier,
    )

    if identity_hash is None:
        return False

    current_time = now or _utc_now()

    window_start = (
        current_time
        - timedelta(minutes=WINDOW_MINUTES)
    )

    failures = db.scalar(
        select(
            func.count(
                AuthenticationFailureAttempt.id
            )
        )
        .where(
            AuthenticationFailureAttempt.flow == flow,
            AuthenticationFailureAttempt.identity_hash
            == identity_hash,
            AuthenticationFailureAttempt.created_at
            > window_start,
        )
    ) or 0

    return failures < MAX_FAILURES


# ==========================================================
# RECORD FAILED AUTHENTICATION
# ==========================================================

def record_failed_attempt(
    db: Session,
    *,
    flow: str,
    identifier: str,
    now: datetime | None = None,
) -> None:
    """Save a failed attempt without sensitive credentials."""

    identity_hash = _fingerprint(
        flow,
        identifier,
    )

    if identity_hash is None:
        return

    db.add(
        AuthenticationFailureAttempt(
            flow=flow,
            identity_hash=identity_hash,
            created_at=now or _utc_now(),
        )
    )

    db.flush()


# ==========================================================
# CLEAR FAILURES FOLLOWING SUCCESSFUL AUTHENTICATION
# ==========================================================

def clear_failed_attempts(
    db: Session,
    *,
    flow: str,
    identifier: str,
) -> None:
    """Reset the rolling failure counter after success."""

    identity_hash = _fingerprint(
        flow,
        identifier,
    )

    if identity_hash is None:
        return

    db.execute(
        delete(AuthenticationFailureAttempt)
        .where(
            AuthenticationFailureAttempt.flow == flow,
            AuthenticationFailureAttempt.identity_hash
            == identity_hash,
        )
    )

# ==========================================================
# SPRINT 11B.5C — ATOMIC SQLITE AUTHENTICATION
# ==========================================================

def acquire_authentication_lock(
    db: Session,
) -> None:
    """
    Start an immediate SQLite write transaction.

    This must be the first database operation
    performed in a fresh session.

    SQLite allows one writer at a time. Acquiring
    the write reservation before checking the
    failure counter ensures concurrent requests
    cannot bypass the same rate limit.

    This implementation is deliberately SQLite-only.
    A PostgreSQL deployment requires a separate
    transactional locking implementation.
    """

    if db.in_transaction():
        raise RuntimeError(
            "Authentication lock must be acquired "
            "before any database query."
        )

    bind = db.get_bind()

    if bind.dialect.name != "sqlite":
        raise RuntimeError(
            "Atomic authentication locking is "
            "not configured for this database."
        )

    # Starts BEGIN IMMEDIATE as the first SQL command.
    # The connection waits for an existing SQLite writer
    # up to its configured busy timeout.

    db.connection().exec_driver_sql(
        "BEGIN IMMEDIATE"
    )


# ==========================================================
# SPRINT 11B.6B — READ-ONLY FAILURE STATUS
# ==========================================================

def get_recent_failure_count(
    db: Session,
    *,
    flow: str,
    identifier: str,
    now: datetime | None = None,
) -> int:
    """
    Return the number of failures inside the current
    rolling authentication window.

    Reuses the same fingerprinting and time policy
    as the existing authentication rate limiter.

    Does not change account state or failure records.
    """

    identity_hash = _fingerprint(
        flow,
        identifier,
    )

    if identity_hash is None:
        return 0

    current_time = now or _utc_now()

    window_start = (
        current_time
        - timedelta(minutes=WINDOW_MINUTES)
    )

    count = db.scalar(
        select(
            func.count(
                AuthenticationFailureAttempt.id
            )
        )
        .where(
            AuthenticationFailureAttempt.flow == flow,
            AuthenticationFailureAttempt.identity_hash
            == identity_hash,
            AuthenticationFailureAttempt.created_at
            > window_start,
        )
    )
    return int(count or 0)