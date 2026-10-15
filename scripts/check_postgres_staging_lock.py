
"""Verify real PostgreSQL authentication locking.

Blue Moon Apartments — Sprint 12C.6

This script:
- Uses the existing direct Neon connection settings.
- Verifies the expected application tables.
- Opens two independent PostgreSQL sessions.
- Acquires the real authentication advisory lock.
- Verifies another transaction cannot acquire it.
- Verifies rollback releases the lock.
- Does not insert, update, or delete application records.
- Does not connect through the application's SQLite session.

Usage:
    python -m scripts.check_postgres_staging_lock
"""

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database.models import Base

from scripts.create_postgres_staging_schema import (
    read_staging_url,
    create_staging_engine,
)

from services.auth_throttle_service import (
    acquire_authentication_lock,
    AUTHENTICATION_PG_LOCK_KEY,
)


TRY_LOCK_SQL = text(
    "SELECT pg_try_advisory_xact_lock(:lock_key)"
)


def verify_schema(engine):
    """Verify application tables exist in PostgreSQL."""

    expected = {
        table.name
        for table in Base.metadata.tables.values()
    }

    with engine.connect() as connection:
        actual = set(
            inspect(connection).get_table_names(
                schema="public"
            )
        )

    if expected != actual:
        raise RuntimeError(
            "PostgreSQL application schema does "
            "not match the SQLAlchemy models. "
            f"Expected {len(expected)} tables, "
            f"found {len(actual)}."
        )

    print(
        "PostgreSQL tables verified:",
        len(actual),
    )


def try_authentication_lock(db):
    """Attempt a nonblocking transaction-level lock."""

    return db.scalar(
        TRY_LOCK_SQL,
        {
            "lock_key": AUTHENTICATION_PG_LOCK_KEY,
        },
    )


def verify_locking(engine):
    """Check lock exclusivity and rollback release."""

    # Two distinct sessions use separate connections.
    with Session(engine) as session_a:
        with Session(engine) as session_b:

            print(
                "\nTest 1: Acquire authentication lock"
            )

            acquire_authentication_lock(
                session_a
            )

            assert session_a.in_transaction()

            print("PASS: Session A acquired lock.")

            # ------------------------------------------
            # LOCK CONTENTION
            # ------------------------------------------

            print(
                "\nTest 2: Reject competing lock"
            )

            competing_result = (
                try_authentication_lock(
                    session_b
                )
            )

            if competing_result is not False:
                raise RuntimeError(
                    "Authentication lock did not "
                    "prevent concurrent ownership."
                )

            print(
                "PASS: Session B cannot acquire "
                "the lock while A holds it."
            )

            # ------------------------------------------
            # TRANSACTION ROLLBACK
            # ------------------------------------------

            print(
                "\nTest 3: Release lock on rollback"
            )

            session_a.rollback()

            released_result = (
                try_authentication_lock(
                    session_b
                )
            )

            if released_result is not True:
                raise RuntimeError(
                    "Authentication lock was not "
                    "released after rollback."
                )

            print(
                "PASS: Session B acquired the "
                "lock after A rolled back."
            )

            # ------------------------------------------
            # SECOND ROLLBACK
            # ------------------------------------------

            print(
                "\nTest 4: Verify second lock release"
            )

            session_b.rollback()

            reacquired_result = (
                try_authentication_lock(
                    session_a
                )
            )

            if reacquired_result is not True:
                raise RuntimeError(
                    "Authentication lock was not "
                    "released by Session B."
                )

            print(
                "PASS: Session A reacquired "
                "the released lock."
            )

            session_a.rollback()


def main():
    print("=" * 55)
    print("BLUE MOON APARTMENTS")
    print("PostgreSQL Authentication Lock Verification")
    print("=" * 55)

    url = read_staging_url()
    engine = create_staging_engine(url)

    try:
        verify_schema(engine)
        verify_locking(engine)

        print("\n" + "=" * 55)
        print("SUCCESS: PostgreSQL locking checks passed.")
        print("=" * 55)

        print(
            "Authentication lock: verified"
        )
        print(
            "Transaction isolation: verified for lock ownership"
        )
        print(
            "Rollback releases lock: verified"
        )
        print(
            "Application records: unchanged"
        )
        print(
            "Local SQLite database: unchanged"
        )

    except RuntimeError as exc:
        print(
            "\nVerification failed:",
            str(exc),
        )
        raise SystemExit(1) from None

    except SQLAlchemyError as exc:
        print(
            "\nDatabase verification failed:",
            type(exc).__name__,
        )
        raise SystemExit(1) from None

    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
