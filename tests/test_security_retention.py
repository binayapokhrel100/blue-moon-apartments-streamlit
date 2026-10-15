
"""Sprint 11B.6A — security retention and cleanup tests."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.models import (
    AdminRoleChangeEvent,
    AuthenticationFailureAttempt,
    Base,
    LoginEvent,
    User,
)

from services import security_retention_service as retention


TEST_NOW = datetime(2026, 10, 14, 17, 0)


# ==========================================================
# ISOLATED TEST DATABASE
# ==========================================================

@pytest.fixture()
def retention_env(monkeypatch):

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={
            "check_same_thread": False,
        },
        poolclass=StaticPool,
    )

    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    @contextmanager
    def test_session():

        with SessionLocal() as db:
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    monkeypatch.setattr(
        retention,
        "get_db_session",
        test_session,
    )

    with test_session() as db:

        user = User(
            first_name="Retention",
            last_name="Tester",
            email="retention@example.test",
            password_hash="unchanged-password-hash",
            role="admin",
            is_active=True,
        )

        db.add(user)
        db.flush()

        user_id = user.id

        # Login events:
        # 181 days old -> eligible for deletion.
        # 180 days old -> exactly on boundary.
        # 179 days old -> must be preserved.

        for days in [181, 180, 179]:
            db.add(
                LoginEvent(
                    user_id=user_id,
                    event_type="login_success",
                    success=True,
                    created_at=(
                        TEST_NOW - timedelta(days=days)
                    ),
                )
            )

        # Authentication failure attempts:
        # 31 days old -> eligible.
        # 30 days old -> exactly on boundary.
        # 29 days old -> must be preserved.

        for days in [31, 30, 29]:
            db.add(
                AuthenticationFailureAttempt(
                    flow="admin_login",
                    identity_hash="a" * 64,
                    created_at=(
                        TEST_NOW - timedelta(days=days)
                    ),
                )
            )

        # Administrator role-change history must
        # never be touched by this cleanup service.

        db.add(
            AdminRoleChangeEvent(
                actor_user_id=user_id,
                target_user_id=user_id,
                previous_role=None,
                new_role="super_admin",
                action="role_assigned",
                reason="Original administrator audit record",
                created_at=(
                    TEST_NOW - timedelta(days=500)
                ),
            )
        )

    yield {
        "session": test_session,
        "user_id": user_id,
    }

    engine.dispose()


# ==========================================================
# COUNT HELPERS
# ==========================================================

def _count(db, model):

    return int(
        db.scalar(
            select(func.count())
            .select_from(model)
        ) or 0
    )


# ==========================================================
# TEST 1 — PREVIEW DOES NOT MODIFY DATABASE
# ==========================================================

def test_preview_is_read_only(retention_env):

    preview = retention.preview_security_retention(
        now=TEST_NOW,
    )

    assert preview["eligible_login_events"] == 1
    assert preview["eligible_failure_attempts"] == 1

    with retention_env["session"]() as db:

        assert _count(db, LoginEvent) == 3
        assert _count(
            db,
            AuthenticationFailureAttempt,
        ) == 3


# ==========================================================
# TEST 2 — DELETION REQUIRES CONFIRMATION
# ==========================================================

def test_cleanup_requires_explicit_confirmation(
    retention_env,
):

    with pytest.raises(
        ValueError,
        match="Explicit confirmation",
    ):
        retention.cleanup_security_retention(
            now=TEST_NOW,
        )

    with retention_env["session"]() as db:
        assert _count(db, LoginEvent) == 3


# ==========================================================
# TEST 3 — ONLY EXPIRED RECORDS ARE DELETED
# ==========================================================

def test_cleanup_preserves_recent_records(
    retention_env,
):

    result = retention.cleanup_security_retention(
        confirm=True,
        now=TEST_NOW,
    )

    assert result["deleted_login_events"] == 1
    assert result["deleted_failure_attempts"] == 1

    assert (
        result["remaining_eligible_login_events"]
        == 0
    )

    assert (
        result["remaining_eligible_failure_attempts"]
        == 0
    )

    with retention_env["session"]() as db:

        assert _count(db, LoginEvent) == 2

        assert _count(
            db,
            AuthenticationFailureAttempt,
        ) == 2


# ==========================================================
# TEST 4 — ADMIN ROLE AUDIT HISTORY IS PRESERVED
# ==========================================================

def test_role_audit_and_user_password_are_preserved(
    retention_env,
):

    retention.cleanup_security_retention(
        confirm=True,
        now=TEST_NOW,
    )

    with retention_env["session"]() as db:

        assert _count(
            db,
            AdminRoleChangeEvent,
        ) == 1

        user = db.get(
            User,
            retention_env["user_id"],
        )

        assert user.password_hash == (
            "unchanged-password-hash"
        )

        assert user.is_active is True


# ==========================================================
# TEST 5 — BATCH LIMIT IS RESPECTED
# ==========================================================

def test_cleanup_respects_batch_limit(
    retention_env,
):

    with retention_env["session"]() as db:

        db.add(
            LoginEvent(
                user_id=retention_env["user_id"],
                event_type="login_success",
                success=True,
                created_at=(
                    TEST_NOW - timedelta(days=190)
                ),
            )
        )

        db.add(
            AuthenticationFailureAttempt(
                flow="admin_login",
                identity_hash="b" * 64,
                created_at=(
                    TEST_NOW - timedelta(days=40)
                ),
            )
        )

    result = retention.cleanup_security_retention(
        confirm=True,
        batch_size=1,
        now=TEST_NOW,
    )

    assert result["deleted_login_events"] == 1
    assert result["deleted_failure_attempts"] == 1

    assert (
        result["remaining_eligible_login_events"]
        == 1
    )

    assert (
        result["remaining_eligible_failure_attempts"]
        == 1
    )


# ==========================================================
# TEST 6 — TIMEZONE-AWARE DATES ARE NORMALIZED
# ==========================================================

def test_timezone_aware_now_is_supported(
    retention_env,
):

    aware_now = TEST_NOW.replace(
        tzinfo=timezone.utc
    )

    preview = retention.preview_security_retention(
        now=aware_now,
    )

    assert preview["login_event_cutoff"] == (
        TEST_NOW - timedelta(days=180)
    )

    assert preview["failure_attempt_cutoff"] == (
        TEST_NOW - timedelta(days=30)
    )


# ==========================================================
# TEST 7 — UNSAFE RETENTION PERIODS ARE REJECTED
# ==========================================================

def test_unsafe_retention_periods_are_rejected(
    retention_env,
):

    with pytest.raises(ValueError):
        retention.preview_security_retention(
            login_days=1,
            now=TEST_NOW,
        )

    with pytest.raises(ValueError):
        retention.preview_security_retention(
            attempt_days=0,
            now=TEST_NOW,
        )

    with pytest.raises(ValueError):
        retention.cleanup_security_retention(
            confirm=True,
            batch_size=5001,
            now=TEST_NOW,
        )
