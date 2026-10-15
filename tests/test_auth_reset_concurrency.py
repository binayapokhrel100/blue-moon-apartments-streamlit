
"""Sprint 11B.5C — atomic reset and authentication audit tests."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Barrier

import pytest

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from core.security import hash_password

from database.models import (
    AdminCredentialState,
    AdminEmployee,
    AuthenticationFailureAttempt,
    Base,
    LoginEvent,
    User,
)

from services import admin_rbac_service, auth_service

from services.auth_throttle_service import (
    record_failed_attempt,
)


OWNER_EMAIL = "atomic.owner@example.test"
TARGET_EMAIL = "atomic.employee@example.test"

OWNER_PASSWORD = "OwnerPassword123!"
INITIAL_PASSWORD = "InitialPassword123!"
NEW_PASSWORD = "UpdatedPassword456!"

TARGET_EMPLOYEE_ID = "BM-ATOMIC-RESET-101"


# ==========================================================
# TEMPORARY DATABASE
# ==========================================================

@pytest.fixture()
def reset_atomic_env(tmp_path, monkeypatch):

    database_file = (
        tmp_path / "atomic_reset.sqlite"
    )

    engine = create_engine(
        f"sqlite+pysqlite:///{database_file.as_posix()}",
        connect_args={
            "check_same_thread": False,
            "timeout": 30,
        },
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
        admin_rbac_service,
        "get_db_session",
        test_session,
    )

    monkeypatch.setattr(
        auth_service,
        "get_db_session",
        test_session,
    )

    # Create initial Super Admin account.

    with test_session() as db:

        owner = User(
            first_name="Atomic",
            last_name="Owner",
            email=OWNER_EMAIL,
            password_hash=hash_password(
                OWNER_PASSWORD
            ),
            role="admin",
            is_active=True,
        )

        db.add(owner)
        db.flush()

        db.add(
            AdminEmployee(
                user_id=owner.id,
                employee_id="BM-OWNER-999",
                is_active=True,
            )
        )

        owner_id = owner.id

    admin_rbac_service.bootstrap_initial_super_admin(
        OWNER_EMAIL
    )

    # Create a separate employee for recovery tests.

    target_id = admin_rbac_service.create_admin_employee(
        actor_id=owner_id,
        first_name="Atomic",
        last_name="Employee",
        email=TARGET_EMAIL,
        employee_id=TARGET_EMPLOYEE_ID,
        password=INITIAL_PASSWORD,
        role="leasing_agent",
        reason="Creating an account for atomic recovery testing",
    )

    yield {
        "owner": owner_id,
        "target": target_id,
        "session": test_session,
    }

    engine.dispose()


# ==========================================================
# TEST HELPERS
# ==========================================================

def _issue_code(env):

    return admin_rbac_service.request_admin_password_reset(
        actor_id=env["owner"],
        target_admin_id=env["target"],
        reason="Verified employee identity before reset",
        identity_verified=True,
        verification_method="in_person",
        delivery_method="in_person",

    )


def _redeem(code):

    return admin_rbac_service.redeem_admin_password_reset(
        email=TARGET_EMAIL,
        employee_id=TARGET_EMPLOYEE_ID,
        reset_code=code,
        new_password=NEW_PASSWORD,
        confirm_password=NEW_PASSWORD,
    )


def _count_failures(env, flow):

    with env["session"]() as db:

        return int(
            db.scalar(
                select(
                    func.count(
                        AuthenticationFailureAttempt.id
                    )
                ).where(
                    AuthenticationFailureAttempt.flow
                    == flow
                )
            ) or 0
        )


def _count_events(env, event_type):

    with env["session"]() as db:

        return int(
            db.scalar(
                select(
                    func.count(LoginEvent.id)
                ).where(
                    LoginEvent.event_type == event_type
                )
            ) or 0
        )


# ==========================================================
# TEST 1 — RESET CODE CANNOT SUCCEED TWICE
# ==========================================================

def test_concurrent_redemption_succeeds_only_once(
    reset_atomic_env,
):

    code = _issue_code(reset_atomic_env)

    worker_count = 6
    barrier = Barrier(worker_count)

    def attempt(_):

        barrier.wait(timeout=20)

        try:
            _redeem(code)
            return True

        except ValueError:
            return False

    with ThreadPoolExecutor(
        max_workers=worker_count
    ) as executor:

        results = list(
            executor.map(
                attempt,
                range(worker_count),
            )
        )

    assert results.count(True) == 1
    assert results.count(False) == 5

    assert _count_events(
        reset_atomic_env,
        "password_reset_completed",
    ) == 1

    # Code consumed after the first successful use.

    with reset_atomic_env["session"]() as db:

        state = db.get(
            AdminCredentialState,
            reset_atomic_env["target"],
        )

        assert state.reset_token_hash is None
        assert state.reset_expires_at is None


# ==========================================================
# TEST 2 — CONCURRENT WRONG CODES CANNOT BYPASS LIMIT
# ==========================================================

def test_concurrent_invalid_codes_respect_five_attempt_limit(
    reset_atomic_env,
):

    valid_code = _issue_code(
        reset_atomic_env
    )

    worker_count = 9
    barrier = Barrier(worker_count)

    def attempt(_):

        barrier.wait(timeout=20)

        try:
            _redeem("incorrect-reset-code")
            return True

        except ValueError:
            return False

    with ThreadPoolExecutor(
        max_workers=worker_count
    ) as executor:

        results = list(
            executor.map(
                attempt,
                range(worker_count),
            )
        )

    assert not any(results)

    # The limiter records at most five rejected
    # code validations before blocking others.

    assert _count_failures(
        reset_atomic_env,
        "admin_reset",
    ) == 5

    # The real code remains stored but temporarily
    # cannot be redeemed after reaching the limit.

    with pytest.raises(
        ValueError,
        match="Invalid or expired",
    ):
        _redeem(valid_code)


# ==========================================================
# TEST 3 — RECOVERY CLEARS OLD ADMIN LOGIN LOCKOUTS
# ==========================================================

def test_successful_recovery_clears_login_failures(
    reset_atomic_env,
):

    with reset_atomic_env["session"]() as db:

        for _ in range(5):

            record_failed_attempt(
                db,
                flow="admin_login",
                identifier=TARGET_EMAIL,
            )

    assert _count_failures(
        reset_atomic_env,
        "admin_login",
    ) == 5

    code = _issue_code(
        reset_atomic_env
    )

    _redeem(code)

    assert _count_failures(
        reset_atomic_env,
        "admin_login",
    ) == 0

    assert _count_failures(
        reset_atomic_env,
        "admin_reset",
    ) == 0

    # The employee can immediately use the
    # recovered password to sign in.

    user = auth_service.authenticate_admin(
        TARGET_EMAIL,
        TARGET_EMPLOYEE_ID,
        NEW_PASSWORD,
    )

    assert user is not None
    assert user.email == TARGET_EMAIL


# ==========================================================
# TEST 4 — FAILED AND BLOCKED LOGIN AUDIT
# ==========================================================

def test_failed_and_blocked_login_events_are_recorded(
    reset_atomic_env,
):

    for _ in range(6):

        result = auth_service.authenticate_admin(
            TARGET_EMAIL,
            TARGET_EMPLOYEE_ID,
            "IncorrectPassword123!",
        )

        assert result is None

    # The five rejected credential attempts should
    # create five security failure events.

    assert _count_events(
        reset_atomic_env,
        "admin_login_failed",
    ) == 5

    # The sixth attempt is blocked by rate limiting.

    assert _count_events(
        reset_atomic_env,
        "admin_login_blocked",
    ) >= 1


# ==========================================================
# TEST 5 — RESET SECURITY AUDIT
# ==========================================================

def test_invalid_and_successful_reset_events_are_recorded(
    reset_atomic_env,
):

    code = _issue_code(reset_atomic_env)

    with pytest.raises(
        ValueError,
        match="Invalid or expired",
    ):
        _redeem(
            "incorrect-reset-code"
        )

    assert _count_events(
        reset_atomic_env,
        "admin_reset_failed",
    ) == 1

    _redeem(code)

    assert _count_events(
        reset_atomic_env,
        "password_reset_completed",
    ) == 1


# ==========================================================
# TEST 6 — UNKNOWN ACCOUNT DOES NOT CREATE USER AUDIT
# ==========================================================

def test_unknown_email_does_not_create_user_linked_event(
    reset_atomic_env,
):

    before = _count_events(
        reset_atomic_env,
        "admin_login_failed",
    )

    result = auth_service.authenticate_admin(
        "unknown.account@example.test",
        "BM-UNKNOWN",
        "IncorrectPassword123!",
    )

    assert result is None

    after = _count_events(
        reset_atomic_env,
        "admin_login_failed",
    )

    assert after == before

    # Unknown-account failures still enter the
    # hashed rate-limiting table.

    assert _count_failures(
        reset_atomic_env,
        "admin_login",
    ) == 1
