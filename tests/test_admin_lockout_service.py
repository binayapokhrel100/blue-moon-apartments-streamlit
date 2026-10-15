
"""Tests for audited administrator login lockout recovery."""

from contextlib import contextmanager

import pytest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from core.security import hash_password

from database.models import (
    AdminEmployee,
    AdminRoleChangeEvent,
    Base,
    LoginEvent,
    User,
)

from services import (
    admin_lockout_service,
    admin_rbac_service,
    auth_service,
)

from services.auth_throttle_service import (
    get_recent_failure_count,
    record_failed_attempt,
)


OWNER_EMAIL = "lockout.owner@example.test"
TARGET_EMAIL = "lockout.employee@example.test"

OWNER_PASSWORD = "OwnerPassword123!"
TARGET_PASSWORD = "EmployeePassword123!"

TARGET_EMPLOYEE_ID = "BM-LOCKOUT-101"

VALID_REASON = (
    "Employee identity verified through the "
    "approved in-person verification process."
)


# ==========================================================
# ISOLATED DATABASE FIXTURE
# ==========================================================

@pytest.fixture()
def lockout_env(tmp_path, monkeypatch):

    database_file = (
        tmp_path / "admin_lockout_test.sqlite"
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
        admin_lockout_service,
        "get_db_session",
        test_session,
    )

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

    # ------------------------------------------
    # CREATE INITIAL SUPER ADMIN
    # ------------------------------------------

    with test_session() as db:

        owner = User(
            first_name="Lockout",
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

        owner_id = owner.id

        db.add(
            AdminEmployee(
                user_id=owner_id,
                employee_id="BM-LOCKOUT-OWNER",
                is_active=True,
            )
        )

    admin_rbac_service.bootstrap_initial_super_admin(
        OWNER_EMAIL
    )

    # ------------------------------------------
    # CREATE EMPLOYEE
    # ------------------------------------------

    target_id = admin_rbac_service.create_admin_employee(
        actor_id=owner_id,
        first_name="Lockout",
        last_name="Employee",
        email=TARGET_EMAIL,
        employee_id=TARGET_EMPLOYEE_ID,
        password=TARGET_PASSWORD,
        role="leasing_agent",
        reason="Approved account for administrator lockout tests",
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

def _record_failures(
    env,
    *,
    flow="admin_login",
    email=TARGET_EMAIL,
    count=5,
):

    with env["session"]() as db:

        for _ in range(count):

            record_failed_attempt(
                db,
                flow=flow,
                identifier=email,
            )


def _failure_count(
    env,
    *,
    flow="admin_login",
    email=TARGET_EMAIL,
):

    with env["session"]() as db:

        return get_recent_failure_count(
            db,
            flow=flow,
            identifier=email,
        )


def _unlock(env):

    return admin_lockout_service.unlock_admin_login(
        actor_id=env["owner"],
        target_admin_id=env["target"],
        reason=VALID_REASON,
        identity_verified=True,
    )


# ==========================================================
# TEST 1 — UNLOCK STATUS
# ==========================================================

def test_lockout_status_is_reported_correctly(lockout_env):

    status = (
        admin_lockout_service
        .get_admin_login_lockout_status(
            lockout_env["owner"],
            lockout_env["target"],
        )
    )

    assert status["is_locked"] is False
    assert status["failed_attempts"] == 0
    assert status["max_attempts"] == 5

    _record_failures(lockout_env)

    status = (
        admin_lockout_service
        .get_admin_login_lockout_status(
            lockout_env["owner"],
            lockout_env["target"],
        )
    )

    assert status["is_locked"] is True
    assert status["failed_attempts"] == 5
    assert status["window_minutes"] == 15


# ==========================================================
# TEST 2 — SUPER ADMIN UNLOCK
# ==========================================================

def test_super_admin_can_unlock_verified_employee(
    lockout_env,
):

    _record_failures(lockout_env)

    result = _unlock(lockout_env)

    assert result["unlocked"] is True
    assert result["cleared_failures"] == 5

    assert _failure_count(lockout_env) == 0

    with lockout_env["session"]() as db:

        audit = db.scalar(
            select(AdminRoleChangeEvent)
            .where(
                AdminRoleChangeEvent.action
                == "login_unlocked"
            )
        )

        assert audit is not None
        assert audit.actor_user_id == lockout_env["owner"]
        assert audit.target_user_id == lockout_env["target"]

        event = db.scalar(
            select(LoginEvent)
            .where(
                LoginEvent.event_type
                == "admin_login_unlocked"
            )
        )

        assert event is not None
        assert event.user_id == lockout_env["target"]


# ==========================================================
# TEST 3 — CORRECT PASSWORD STILL REQUIRED
# ==========================================================

def test_unlock_does_not_bypass_password(
    lockout_env,
):

    # New employees start with mandatory password
    # change but can authenticate normally.

    _record_failures(lockout_env)
    _unlock(lockout_env)

    assert auth_service.authenticate_admin(
        TARGET_EMAIL,
        TARGET_EMPLOYEE_ID,
        "WrongPassword123!",
    ) is None

    assert auth_service.authenticate_admin(
        TARGET_EMAIL,
        TARGET_EMPLOYEE_ID,
        TARGET_PASSWORD,
    ) is not None


# ==========================================================
# TEST 4 — SELF UNLOCK REJECTED
# ==========================================================

def test_super_admin_cannot_unlock_self(lockout_env):

    _record_failures(
        lockout_env,
        email=OWNER_EMAIL,
    )

    with pytest.raises(
        PermissionError,
        match="cannot unlock",
    ):

        admin_lockout_service.unlock_admin_login(
            actor_id=lockout_env["owner"],
            target_admin_id=lockout_env["owner"],
            reason=VALID_REASON,
            identity_verified=True,
        )

    assert _failure_count(
        lockout_env,
        email=OWNER_EMAIL,
    ) == 5


# ==========================================================
# TEST 5 — IDENTITY VERIFICATION REQUIRED
# ==========================================================

def test_identity_verification_is_required(lockout_env):

    _record_failures(lockout_env)

    with pytest.raises(
        ValueError,
        match="verification",
    ):

        admin_lockout_service.unlock_admin_login(
            actor_id=lockout_env["owner"],
            target_admin_id=lockout_env["target"],
            reason=VALID_REASON,
            identity_verified=False,
        )

    assert _failure_count(lockout_env) == 5


# ==========================================================
# TEST 6 — UNLOCK REQUIRES ACTIVE LOCKOUT
# ==========================================================

def test_unlock_without_lockout_is_rejected(lockout_env):

    with pytest.raises(
        ValueError,
        match="does not have",
    ):
        _unlock(lockout_env)


# ==========================================================
# TEST 7 — PENDING RESET CANNOT BE BYPASSED
# ==========================================================

def test_pending_password_reset_cannot_be_bypassed(
    lockout_env,
):

    _record_failures(lockout_env)

    admin_rbac_service.request_admin_password_reset(
        actor_id=lockout_env["owner"],
        target_admin_id=lockout_env["target"],
        reason="Verified identity for password recovery",
        identity_verified=True,
        verification_method="in_person",
        delivery_method="in_person",

    )

    with pytest.raises(
        ValueError,
        match="pending password reset",
    ):
        _unlock(lockout_env)

    assert _failure_count(lockout_env) == 5


# ==========================================================
# TEST 8 — OTHER FAILURE COUNTERS ARE PRESERVED
# ==========================================================

def test_unlock_clears_only_admin_login_failures(
    lockout_env,
):

    _record_failures(lockout_env)

    _record_failures(
        lockout_env,
        flow="admin_reset",
        count=2,
    )

    _record_failures(
        lockout_env,
        flow="resident_login",
        count=2,
    )

    _unlock(lockout_env)

    assert _failure_count(
        lockout_env,
        flow="admin_login",
    ) == 0

    assert _failure_count(
        lockout_env,
        flow="admin_reset",
    ) == 2

    assert _failure_count(
        lockout_env,
        flow="resident_login",
    ) == 2


# ==========================================================
# TEST 9 — FAILED AUDIT ROLLS BACK UNLOCK
# ==========================================================

def test_audit_failure_rolls_back_unlock(
    lockout_env,
    monkeypatch,
):

    _record_failures(lockout_env)

    def fail_audit(*args, **kwargs):
        raise RuntimeError("Audit unavailable")

    monkeypatch.setattr(
        admin_lockout_service,
        "_audit",
        fail_audit,
    )

    with pytest.raises(
        RuntimeError,
        match="Audit unavailable",
    ):
        _unlock(lockout_env)

    assert _failure_count(lockout_env) == 5


# ==========================================================
# TEST 10 — NON SUPER ADMIN REJECTED
# ==========================================================

def test_non_super_admin_cannot_unlock_employee(
    lockout_env,
):

    actor_id = admin_rbac_service.create_admin_employee(
        actor_id=lockout_env["owner"],
        first_name="Property",
        last_name="Manager",
        email="lockout.manager@example.test",
        employee_id="BM-LOCKOUT-MANAGER",
        password="ManagerPassword123!",
        role="property_manager",
        reason="Approved property manager for testing",
    )

    _record_failures(lockout_env)

    with pytest.raises(PermissionError):

        admin_lockout_service.unlock_admin_login(
            actor_id=actor_id,
            target_admin_id=lockout_env["target"],
            reason=VALID_REASON,
            identity_verified=True,
        )

    assert _failure_count(lockout_env) == 5
