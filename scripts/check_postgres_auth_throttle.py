
"""Real PostgreSQL authentication throttling integration test.

Blue Moon Apartments — Sprint 12C.7

This script:
- Uses the Direct Neon staging connection.
- Checks the existing 24-table application schema.
- Requires an empty users table.
- Tests transaction rollback.
- Tests seven simultaneous authentication attempts.
- Verifies the five-failure rate limit.
- Verifies failure-counter cleanup.
- Uses a random fictional identifier.
- Does not create user or administrator accounts.
- Does not modify local SQLite data.
- Cleans up its own temporary failure records.

Usage:
    python -m scripts.check_postgres_auth_throttle
"""

import secrets

from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from threading import Barrier

from sqlalchemy import func, inspect, select, text
from sqlalchemy.orm import Session

from database.models import (
    Base,
    AuthenticationFailureAttempt,
    User,
)

from scripts.create_postgres_staging_schema import (
    create_staging_engine,
    read_staging_url,
)

from services.auth_throttle_service import (
    MAX_FAILURES,
    acquire_authentication_lock,
    clear_failed_attempts,
    get_recent_failure_count,
    is_attempt_allowed,
    record_failed_attempt,
)


FLOW = "admin_login"
CONCURRENT_ATTEMPTS = 7


def identity_fingerprint(identifier: str) -> str:
    """Derive the same fingerprint used by the rate limiter."""

    normalized = identifier.strip().casefold()
    payload = f"{FLOW}\x00{normalized}"

    return sha256(
        payload.encode("utf-8")
    ).hexdigest()


def verify_staging_database(engine):
    """Verify schema and reject populated user databases."""

    expected = {
        table.name
        for table in Base.metadata.tables.values()
    }

    with engine.connect() as connection:

        database_name = connection.scalar(
            text("SELECT current_database()")
        )

        existing_tables = set(
            inspect(connection).get_table_names(
                schema="public"
            )
        )

        existing_users = connection.scalar(
            select(func.count(User.id))
        )

    if existing_tables != expected:
        raise RuntimeError(
            "Staging schema does not match "
            "the application models."
        )

    if existing_users != 0:
        raise RuntimeError(
            "The staging database contains users. "
            "Use a separate empty test database."
        )

    print("Database:", database_name)
    print("Application tables:", len(existing_tables))
    print("Existing users:", existing_users)

    return database_name


def failure_count(engine, identifier):
    """Read the current failure count from a fresh session."""

    with Session(engine) as db:
        return get_recent_failure_count(
            db,
            flow=FLOW,
            identifier=identifier,
        )


def test_transaction_rollback(engine, identifier):
    """Verify uncommitted failures disappear on rollback."""

    print("\nTest 1: Transaction rollback")

    with Session(engine) as db:

        acquire_authentication_lock(db)

        record_failed_attempt(
            db,
            flow=FLOW,
            identifier=identifier,
        )

        count = get_recent_failure_count(
            db,
            flow=FLOW,
            identifier=identifier,
        )

        if count != 1:
            raise RuntimeError(
                "Uncommitted failure record "
                "was not visible in its transaction."
            )

        db.rollback()

    remaining = failure_count(
        engine,
        identifier,
    )

    if remaining != 0:
        raise RuntimeError(
            "Rollback failed to remove "
            "the uncommitted failure record."
        )

    print("PASS: Rollback removed uncommitted failure.")


def test_concurrent_throttling(engine, identifier):
    """Test the rate limiter using real concurrent sessions."""

    print(
        "\nTest 2: Concurrent authentication attempts"
    )

    barrier = Barrier(CONCURRENT_ATTEMPTS)

    def attempt(_):
        """Execute one locked authentication failure check."""

        barrier.wait(timeout=30)

        with Session(engine) as db:

            try:
                acquire_authentication_lock(db)

                allowed = is_attempt_allowed(
                    db,
                    flow=FLOW,
                    identifier=identifier,
                )

                if allowed:
                    record_failed_attempt(
                        db,
                        flow=FLOW,
                        identifier=identifier,
                    )

                db.commit()

                return allowed

            except Exception:
                db.rollback()
                raise

    with ThreadPoolExecutor(
        max_workers=CONCURRENT_ATTEMPTS
    ) as executor:

        results = list(
            executor.map(
                attempt,
                range(CONCURRENT_ATTEMPTS),
            )
        )

    allowed_count = sum(
        1 for result in results if result
    )

    blocked_count = (
        CONCURRENT_ATTEMPTS - allowed_count
    )

    stored_failures = failure_count(
        engine,
        identifier,
    )

    print("Concurrent attempts:", CONCURRENT_ATTEMPTS)
    print("Allowed failures:", allowed_count)
    print("Blocked attempts:", blocked_count)
    print("Stored failure records:", stored_failures)

    if allowed_count != MAX_FAILURES:
        raise RuntimeError(
            "Concurrent rate limiting allowed "
            "an incorrect number of failures."
        )

    if blocked_count != (
        CONCURRENT_ATTEMPTS - MAX_FAILURES
    ):
        raise RuntimeError(
            "Blocked attempt count is incorrect."
        )

    if stored_failures != MAX_FAILURES:
        raise RuntimeError(
            "Persisted failure count is incorrect."
        )

    print(
        "PASS: Concurrent rate limiting "
        "enforced the configured threshold."
    )


def cleanup_test_records(engine, identifier):
    """Remove only records belonging to this test run."""

    fingerprint = identity_fingerprint(
        identifier
    )

    with Session(engine) as db:

        try:
            acquire_authentication_lock(db)

            db.query(
                AuthenticationFailureAttempt
            ).filter(
                AuthenticationFailureAttempt.flow == FLOW,
                AuthenticationFailureAttempt.identity_hash
                == fingerprint,
            ).delete(
                synchronize_session=False
            )

            db.commit()

        except Exception:
            db.rollback()
            raise

    remaining = failure_count(
        engine,
        identifier,
    )

    if remaining != 0:
        raise RuntimeError(
            "Temporary authentication records "
            "were not fully removed."
        )

    print(
        "PASS: Temporary test records removed."
    )


def test_failure_cleanup(engine, identifier):
    """Verify the service can clear recorded failures."""

    print(
        "\nTest 3: Service failure-counter cleanup"
    )

    with Session(engine) as db:

        try:
            acquire_authentication_lock(db)

            clear_failed_attempts(
                db,
                flow=FLOW,
                identifier=identifier,
            )

            db.commit()

        except Exception:
            db.rollback()
            raise

    if failure_count(engine, identifier) != 0:
        raise RuntimeError(
            "Failed-attempt cleanup did not work."
        )

    print(
        "PASS: Service cleared failure records."
    )


def main():
    print("=" * 55)
    print("BLUE MOON APARTMENTS")
    print("PostgreSQL Authentication Throttling Test")
    print("=" * 55)

    url = read_staging_url()
    engine = create_staging_engine(url)

    # Generate a unique fictional identifier.
    identifier = (
        f"pg-test-{secrets.token_hex(12)}"
        "@example.invalid"
    )

    test_started = False

    try:

        database_name = verify_staging_database(
            engine
        )

        confirmation = input(
            "\nType TEST-THROTTLE-"
            + database_name
            + " to run temporary writes: "
        ).strip()

        if confirmation != (
            f"TEST-THROTTLE-{database_name}"
        ):
            print(
                "Cancelled. No records created."
            )
            return

        test_started = True

        test_transaction_rollback(
            engine,
            identifier,
        )

        test_concurrent_throttling(
            engine,
            identifier,
        )

        test_failure_cleanup(
            engine,
            identifier,
        )

        print("\n" + "=" * 55)
        print("SUCCESS: PostgreSQL throttle checks passed.")
        print("=" * 55)

        print("Concurrent attempts:", CONCURRENT_ATTEMPTS)
        print("Failure threshold:", MAX_FAILURES)
        print("Application users created: 0")
        print("Local SQLite database: untouched")

    except Exception as exc:

        print(
            "\nTest failed:",
            type(exc).__name__,
        )

        print(
            "Review staging configuration and "
            "database connectivity."
        )

        raise SystemExit(1) from None

    finally:

        if test_started:
            try:
                cleanup_test_records(
                    engine,
                    identifier,
                )
            except Exception as exc:
                print(
                    "WARNING: Automatic cleanup failed:",
                    type(exc).__name__,
                )
                print(
                    "Do not rerun until staging "
                    "cleanup is investigated."
                )

        engine.dispose()


if __name__ == "__main__":
    main()
