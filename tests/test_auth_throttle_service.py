
"""Tests for database-backed authentication throttling."""

from datetime import datetime, timedelta

import pytest

from sqlalchemy import (
    create_engine,
    func,
    select,
)

from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from database.models import (
    Base,
    AuthenticationFailureAttempt,
)

from services.auth_throttle_service import (
    clear_failed_attempts,
    is_attempt_allowed,
    record_failed_attempt,
)


TEST_TIME = datetime(2026, 10, 14, 19, 0)


@pytest.fixture()
def db():
    """Use an isolated in-memory SQLite database."""

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={
            "check_same_thread": False,
        },
        poolclass=StaticPool,
    )

    Base.metadata.create_all(engine)

    with Session(engine) as session:
        yield session

    engine.dispose()


def _fail(
    db,
    identifier="admin@example.test",
    flow="admin_login",
    now=TEST_TIME,
):
    record_failed_attempt(
        db,
        flow=flow,
        identifier=identifier,
        now=now,
    )


def test_first_login_attempt_allowed(db):
    assert is_attempt_allowed(
        db,
        flow="admin_login",
        identifier="admin@example.test",
        now=TEST_TIME,
    )


def test_four_failures_still_allow_next_attempt(db):
    for _ in range(4):
        _fail(db)

    assert is_attempt_allowed(
        db,
        flow="admin_login",
        identifier="admin@example.test",
        now=TEST_TIME,
    )


def test_five_failures_block_login(db):
    for _ in range(5):
        _fail(db)

    assert not is_attempt_allowed(
        db,
        flow="admin_login",
        identifier="admin@example.test",
        now=TEST_TIME,
    )


def test_lockout_expires_after_window(db):
    for _ in range(5):
        _fail(db)

    assert is_attempt_allowed(
        db,
        flow="admin_login",
        identifier="admin@example.test",
        now=TEST_TIME + timedelta(minutes=16),
    )


def test_email_normalization(db):
    for _ in range(5):
        _fail(
            db,
            identifier=" ADMIN@EXAMPLE.TEST ",
        )

    assert not is_attempt_allowed(
        db,
        flow="admin_login",
        identifier="admin@example.test",
        now=TEST_TIME,
    )


def test_other_users_are_not_blocked(db):
    for _ in range(5):
        _fail(db)

    assert is_attempt_allowed(
        db,
        flow="admin_login",
        identifier="different@example.test",
        now=TEST_TIME,
    )


def test_login_and_reset_have_separate_counters(db):
    for _ in range(5):
        _fail(db)

    assert is_attempt_allowed(
        db,
        flow="admin_reset",
        identifier="admin@example.test",
        now=TEST_TIME,
    )


def test_success_clears_failed_attempts(db):
    for _ in range(5):
        _fail(db)

    clear_failed_attempts(
        db,
        flow="admin_login",
        identifier="admin@example.test",
    )

    assert is_attempt_allowed(
        db,
        flow="admin_login",
        identifier="admin@example.test",
        now=TEST_TIME,
    )


def test_plaintext_email_is_not_stored(db):
    _fail(db)

    value = db.scalar(
        select(
            AuthenticationFailureAttempt.identity_hash
        )
    )

    assert len(value) == 64
    assert "admin@example.test" not in value


def test_invalid_identifier_is_rejected(db):
    assert not is_attempt_allowed(
        db,
        flow="admin_login",
        identifier=" ",
    )

    record_failed_attempt(
        db,
        flow="admin_login",
        identifier="",
    )

    count = db.scalar(
        select(
            func.count(
                AuthenticationFailureAttempt.id
            )
        )
    )

    assert count == 0


def test_unknown_authentication_flow_is_rejected(db):
    with pytest.raises(
        ValueError,
        match="Unsupported authentication flow",
    ):
        is_attempt_allowed(
            db,
            flow="unknown_flow",
            identifier="admin@example.test",
        )
