
"""Tests for offline emergency Super Admin recovery."""

from contextlib import contextmanager
from hashlib import sha256

import pytest

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from core.security import (
    hash_password,
    verify_password,
)

from database.models import (
    AdminCredentialState,
    AdminEmployee,
    Base,
    EmergencySuperAdminRecoveryEvent,
    LoginEvent,
    User,
)

from services import (
    admin_rbac_service,
    emergency_super_admin_service,
)


OWNER_EMAIL = "emergency.owner@example.test"
OWNER_EMPLOYEE_ID = "BM-EMERGENCY-001"

ORIGINAL_PASSWORD = "OriginalPassword123!"
NEW_PASSWORD = "RecoveredPassword456!"

# Test-only key. Never use this value outside tests.
TEST_KEY = (
    "test-only-emergency-recovery-key-not-for-production-"
    "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
)

TEST_HASH = sha256(
    TEST_KEY.encode("utf-8")
).hexdigest()

TEST_REASON = (
    "Authorized emergency recovery after "
    "owner identity verification"
)


# ==========================================================
# TEST DATABASE
# ==========================================================

@pytest.fixture()
def recovery_env(tmp_path, monkeypatch):

    db_file = tmp_path / "emergency_recovery.sqlite"

    engine = create_engine(
        f"sqlite+pysqlite:///{db_file.as_posix()}",
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
        emergency_super_admin_service,
        "get_db_session",
        test_session,
    )

    monkeypatch.setattr(
        admin_rbac_service,
        "get_db_session",
        test_session,
    )

    monkeypatch.setenv(
        emergency_super_admin_service.KEY_HASH_ENV,
        TEST_HASH,
    )

    with test_session() as db:

        owner = User(
            first_name="Emergency",
            last_name="Owner",
            email=OWNER_EMAIL,
            password_hash=hash_password(
                ORIGINAL_PASSWORD
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
                employee_id=OWNER_EMPLOYEE_ID,
                is_active=True,
            )
        )

    admin_rbac_service.bootstrap_initial_super_admin(
        OWNER_EMAIL
    )

    yield {
        "owner": owner_id,
        "session": test_session,
    }

    engine.dispose()


# ==========================================================
# HELPERS
# ==========================================================

def _issue(env, **overrides):

    values = {
        "email": OWNER_EMAIL,
        "employee_id": OWNER_EMPLOYEE_ID,
        "recovery_key": TEST_KEY,
        "operator_label": "trusted-test-operator",
        "ticket_reference": "INC-2026-001",
        "reason": TEST_REASON,
    }

    values.update(overrides)

    return (
        emergency_super_admin_service
        .issue_emergency_super_admin_reset(
            **values,
        )
    )


def _count_recovery_events(env) -> int:

    with env["session"]() as db:

        return int(
            db.scalar(
                select(
                    func.count(
                        EmergencySuperAdminRecoveryEvent.id
                    )
                )
            ) or 0
        )


# ==========================================================
# TEST 1 — PREVIEW IS READ ONLY
# ==========================================================

def test_preview_finds_only_active_super_admin(
    recovery_env,
):

    result = (
        emergency_super_admin_service
        .preview_emergency_super_admin_recovery()
    )

    assert result["eligible"] is True
    assert result["active_super_admin_count"] == 1
    assert result["email"] == OWNER_EMAIL

    assert _count_recovery_events(recovery_env) == 0


# ==========================================================
# TEST 2 — WRONG KEY REJECTED
# ==========================================================

def test_wrong_key_cannot_issue_reset_code(
    recovery_env,
):

    with pytest.raises(
        PermissionError,
        match="authorization failed",
    ):

        _issue(
            recovery_env,
            recovery_key="wrong-" + ("X" * 64),
        )

    assert _count_recovery_events(recovery_env) == 0


# ==========================================================
# TEST 3 — UNCONFIGURED RECOVERY REJECTED
# ==========================================================

def test_unconfigured_recovery_fails_closed(
    recovery_env,
    monkeypatch,
):

    monkeypatch.delenv(
        emergency_super_admin_service.KEY_HASH_ENV,
    )

    with pytest.raises(
        RuntimeError,
        match="not configured",
    ):
        _issue(recovery_env)


# ==========================================================
# TEST 4 — HASHED CODE AND PERMANENT AUDIT
# ==========================================================

def test_valid_emergency_recovery_is_hashed_and_audited(
    recovery_env,
):

    result = _issue(recovery_env)

    code = result["reset_code"]

    with recovery_env["session"]() as db:

        state = db.get(
            AdminCredentialState,
            recovery_env["owner"],
        )

        assert state is not None

        assert state.reset_token_hash == sha256(
            code.encode("utf-8")
        ).hexdigest()

        assert state.must_change_password is True
        assert state.credential_version == 1

        event = db.scalar(
            select(EmergencySuperAdminRecoveryEvent)
        )

        assert event is not None
        assert event.target_user_id == recovery_env["owner"]
        assert event.ticket_reference == "INC-2026-001"

        assert TEST_KEY not in event.reason
        assert code not in event.reason

        assert event.key_fingerprint != TEST_HASH

        login_event = db.scalar(
            select(LoginEvent)
            .where(
                LoginEvent.event_type
                == "emergency_reset_code_issued"
            )
        )

        assert login_event is not None
        assert login_event.success is True


# ==========================================================
# TEST 5 — EMERGENCY KEY IS SINGLE USE
# ==========================================================

def test_emergency_recovery_key_cannot_be_reused(
    recovery_env,
):

    first = _issue(recovery_env)

    with pytest.raises(
        PermissionError,
        match="already been used",
    ):
        _issue(recovery_env)

    with recovery_env["session"]() as db:

        state = db.get(
            AdminCredentialState,
            recovery_env["owner"],
        )

        assert state.reset_token_hash == sha256(
            first["reset_code"].encode("utf-8")
        ).hexdigest()

    assert _count_recovery_events(recovery_env) == 1


# ==========================================================
# TEST 6 — CANNOT TARGET A DIFFERENT ADMINISTRATOR
# ==========================================================

def test_cannot_recover_a_non_super_admin(
    recovery_env,
):

    admin_rbac_service.create_admin_employee(
        actor_id=recovery_env["owner"],
        first_name="Regular",
        last_name="Employee",
        email="emergency.staff@example.test",
        employee_id="BM-EMERGENCY-STAFF",
        password="EmployeePassword123!",
        role="leasing_agent",
        reason="Authorized employee for recovery tests",
    )

    with pytest.raises(
        PermissionError,
        match="sole active Super Admin",
    ):

        _issue(
            recovery_env,
            email="emergency.staff@example.test",
            employee_id="BM-EMERGENCY-STAFF",
        )

    assert _count_recovery_events(recovery_env) == 0


# ==========================================================
# TEST 7 — MULTIPLE SUPER ADMINS DISABLE EMERGENCY PATH
# ==========================================================

def test_multiple_super_admins_disable_emergency_recovery(
    recovery_env,
):

    admin_rbac_service.create_admin_employee(
        actor_id=recovery_env["owner"],
        first_name="Second",
        last_name="Owner",
        email="emergency.second@example.test",
        employee_id="BM-EMERGENCY-002",
        password="SecondOwnerPassword123!",
        role="super_admin",
        reason="Authorized second Super Admin for testing",
    )

    status = (
        emergency_super_admin_service
        .preview_emergency_super_admin_recovery()
    )

    assert status["eligible"] is False
    assert status["active_super_admin_count"] == 2

    with pytest.raises(
        PermissionError,
        match="exactly one",
    ):
        _issue(recovery_env)


# ==========================================================
# TEST 8 — FAILED AUDIT ROLLS BACK RESET
# ==========================================================

def test_audit_failure_rolls_back_emergency_reset(
    recovery_env,
    monkeypatch,
):

    def broken_audit(*args, **kwargs):
        raise RuntimeError("Simulated audit failure")

    monkeypatch.setattr(
        emergency_super_admin_service,
        "_record_recovery_event",
        broken_audit,
    )

    with pytest.raises(
        RuntimeError,
        match="Simulated audit failure",
    ):
        _issue(recovery_env)

    with recovery_env["session"]() as db:

        state = db.get(
            AdminCredentialState,
            recovery_env["owner"],
        )

        assert (
            state is None
            or state.reset_token_hash is None
        )

    assert _count_recovery_events(recovery_env) == 0


# ==========================================================
# TEST 9 — EXISTING REDEMPTION FLOW STILL WORKS
# ==========================================================

def test_emergency_code_uses_existing_reset_redemption(
    recovery_env,
):

    result = _issue(recovery_env)

    admin_rbac_service.redeem_admin_password_reset(
        email=OWNER_EMAIL,
        employee_id=OWNER_EMPLOYEE_ID,
        reset_code=result["reset_code"],
        new_password=NEW_PASSWORD,
        confirm_password=NEW_PASSWORD,
    )

    with recovery_env["session"]() as db:

        owner = db.get(
            User,
            recovery_env["owner"],
        )

        state = db.get(
            AdminCredentialState,
            recovery_env["owner"],
        )

        assert verify_password(
            NEW_PASSWORD,
            owner.password_hash,
        )

        assert state.reset_token_hash is None
        assert state.reset_expires_at is None
        assert state.must_change_password is False

    assert _count_recovery_events(recovery_env) == 1
