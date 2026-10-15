
"""PostgreSQL and SQLite authentication lock tests.

Blue Moon Apartments — Sprint 12C.3

These tests validate dialect selection and generated
PostgreSQL locking SQL without requiring a live
PostgreSQL database.

Real PostgreSQL concurrency testing is required
before cloud deployment.
"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from services.auth_throttle_service import (
    AUTHENTICATION_PG_LOCK_KEY,
    acquire_authentication_lock,
)


def make_fake_session(dialect_name: str):
    """Create a minimal mocked SQLAlchemy session."""

    db = Mock()

    db.in_transaction.return_value = False

    db.get_bind.return_value = SimpleNamespace(
        dialect=SimpleNamespace(
            name=dialect_name
        )
    )

    return db


def test_postgresql_acquires_transaction_advisory_lock():
    """PostgreSQL must use a transaction-scoped lock."""

    db = make_fake_session("postgresql")

    acquire_authentication_lock(db)

    db.execute.assert_called_once()

    statement, parameters = db.execute.call_args.args

    assert (
        str(statement).strip()
        == "SELECT pg_advisory_xact_lock(:lock_key)"
    )

    assert parameters == {
        "lock_key": AUTHENTICATION_PG_LOCK_KEY
    }

    db.connection.assert_not_called()


def test_postgresql_uses_valid_shared_lock_key():
    """The advisory key must fit a signed BIGINT."""

    assert isinstance(
        AUTHENTICATION_PG_LOCK_KEY,
        int,
    )

    assert (
        0
        < AUTHENTICATION_PG_LOCK_KEY
        < 2**63
    )


def test_unsupported_database_is_rejected():
    """Unknown database engines must fail closed."""

    db = make_fake_session("mysql")

    with pytest.raises(
        RuntimeError,
        match="not configured",
    ):
        acquire_authentication_lock(db)

    db.execute.assert_not_called()
    db.connection.assert_not_called()


def test_lock_rejects_existing_transaction():
    """Locking after a database query is forbidden."""

    db = make_fake_session("postgresql")

    db.in_transaction.return_value = True

    with pytest.raises(
        RuntimeError,
        match="before any database query",
    ):
        acquire_authentication_lock(db)

    db.execute.assert_not_called()
    db.connection.assert_not_called()


def test_sqlite_original_lock_behavior_is_preserved():
    """SQLite must still use BEGIN IMMEDIATE."""

    engine = create_engine(
        "sqlite+pysqlite:///:memory:"
    )

    try:
        with Session(engine) as db:

            acquire_authentication_lock(db)

            assert db.in_transaction()

            db.rollback()

    finally:
        engine.dispose()
