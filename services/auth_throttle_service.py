
"""Authentication rate limiting for Blue Moon Apartments."""

from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from hashlib import sha256
from sqlalchemy import delete, func, select, text

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from database.models import AuthenticationFailureAttempt


# ==========================================================
# RATE LIMIT POLICY
# ==========================================================
# Shared transaction-lock identifier for PostgreSQL.
# Must remain the same across every application instance.
AUTHENTICATION_PG_LOCK_KEY = 0x424C55454D4F4F4E
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
    """Acquire an atomic authentication transaction lock.

    SQLite:
        Acquire BEGIN IMMEDIATE before reading any
        authentication or recovery records.

    PostgreSQL:
        Acquire one transaction-scoped advisory lock
        shared by all application instances.

    Requirements:
        - Call only from a fresh database session.
        - Acquire before any authentication DB reads.
        - Keep the lock through the entire operation.
        - Release by committing or rolling back.
        - Reject unsupported database engines.

    A single global PostgreSQL lock intentionally
    preserves the current SQLite-style serialization
    of authentication and recovery operations.
    """

    # --------------------------------------------------
    # REQUIRE A FRESH TRANSACTION
    # --------------------------------------------------

    if db.in_transaction():
        raise RuntimeError(
            "Authentication lock must be acquired "
            "before any database query."
        )

    bind = db.get_bind()
    dialect_name = bind.dialect.name

    # --------------------------------------------------
    # SQLITE — LOCAL DEVELOPMENT
    # --------------------------------------------------

    if dialect_name == "sqlite":

        db.connection().exec_driver_sql(
            "BEGIN IMMEDIATE"
        )

        return

    # --------------------------------------------------
    # POSTGRESQL — CLOUD DEPLOYMENT
    # --------------------------------------------------

    if dialect_name == "postgresql":

        # This statement begins the transaction
        # and blocks until the advisory lock is held.
        #
        # The lock is released automatically when
        # the transaction commits or rolls back.
        #
        # Do not use pg_advisory_lock(), which is
        # session-scoped instead of transaction-scoped.

        db.execute(
            text(
                "SELECT pg_advisory_xact_lock(:lock_key)"
            ),
            {
                "lock_key": AUTHENTICATION_PG_LOCK_KEY,
            },
        )

        return

    # --------------------------------------------------
    # UNSUPPORTED DATABASE — FAIL CLOSED
    # --------------------------------------------------

    raise RuntimeError(
        "Atomic authentication locking is "
        "not configured for this database."
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