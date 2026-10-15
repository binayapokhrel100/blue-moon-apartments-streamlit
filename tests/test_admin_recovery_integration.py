
"""Sprint 11B.6C — secure administrator recovery integration tests."""

from contextlib import contextmanager
from hashlib import sha256

import pytest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from core.security import hash_password

from database.models import (
    AdminCredentialState,
    AdminEmployee,
    AdminRoleChangeEvent,
    Base,
    User,
)

from services import admin_rbac_service


OWNER_EMAIL = "policy.owner@example.test"
TARGET_EMAIL = "policy.employee@example.test"

VERIFIED = {
    "identity_verified": True,
    "verification_method": "in_person",
    "delivery_method": "in_person",
}

REASON = (
    "Identity confirmed face to face "
    "by authorized manager"
)


# ==========================================================
# ISOLATED DATABASE FIXTURE
# ==========================================================

@pytest.fixture()
def recovery_env(tmp_path, monkeypatch):

    database_file = (
        tmp_path / "recovery_policy.sqlite"
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

    # ------------------------------------------
    # CREATE SUPER ADMIN
    # ------------------------------------------

    with test_session() as db:

        owner = User(
            first_name="Policy",
            last_name="Owner",
            email=OWNER_EMAIL,
            password_hash=hash_password(
                "OwnerPassword123!"
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
                employee_id="BM-POLICY-OWNER",
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
        first_name="Policy",
        last_name="Employee",
        email=TARGET_EMAIL,
        employee_id="BM-POLICY-EMPLOYEE",
        password="InitialPassword123!",
        role="leasing_agent",
        reason="Approved for recovery integration test",
    )

    yield {
        "owner": owner_id,
        "target": target_id,
        "session": test_session,
    }

    engine.dispose()


# ==========================================================
# HELPER FOR RESET ISSUANCE
# ==========================================================

def _issue(env, **kwargs):

    return admin_rbac_service.request_admin_password_reset(
        actor_id=env["owner"],
        target_admin_id=env["target"],
        reason=REASON,
        **kwargs,
    )


# ==========================================================
# TEST 1 — VERIFICATION IS REQUIRED
# ==========================================================

def test_missing_verification_is_rejected_without_issuing_code(
    recovery_env,
):

    with pytest.raises(
        ValueError,
        match="verification",
    ):
        _issue(recovery_env)

    with recovery_env["session"]() as db:

        state = db.get(
            AdminCredentialState,
            recovery_env["target"],
        )

        assert state.reset_token_hash is None
        assert state.credential_version == 0


# ==========================================================
# TEST 2 — FALSE VERIFICATION IS REJECTED
# ==========================================================

def test_false_attestation_is_rejected(
    recovery_env,
):

    with pytest.raises(
        ValueError,
        match="verification",
    ):

        _issue(
            recovery_env,
            identity_verified=False,
            verification_method="in_person",
            delivery_method="in_person",
        )


# ==========================================================
# TEST 3 — EMAIL DELIVERY IS REJECTED
# ==========================================================

def test_unapproved_email_delivery_is_rejected(
    recovery_env,
):

    with pytest.raises(
        ValueError,
        match="delivery",
    ):

        _issue(
            recovery_env,
            identity_verified=True,
            verification_method="in_person",
            delivery_method="email",
        )


# ==========================================================
# TEST 4 — CODE IS HASHED AND ISSUANCE IS AUDITED
# ==========================================================

def test_verified_code_is_hashed_and_audited_without_plaintext(
    recovery_env,
):

    code = _issue(
        recovery_env,
        **VERIFIED,
    )

    with recovery_env["session"]() as db:

        state = db.get(
            AdminCredentialState,
            recovery_env["target"],
        )

        assert state.reset_token_hash == (
            sha256(
                code.encode("utf-8")
            ).hexdigest()
        )

        audit = db.scalar(
            select(AdminRoleChangeEvent)
            .where(
                AdminRoleChangeEvent.action
                == "password_reset_requested"
            )
        )

        assert audit is not None

        assert "Verification: In-person" in audit.reason
        assert "Delivery: Delivered in person" in audit.reason

        assert code not in audit.reason

        assert "Reason:" in audit.reason


# ==========================================================
# TEST 5 — APPROVED CALLBACK AND VOICE CALL
# ==========================================================

def test_callback_and_verified_voice_call_allowed(
    recovery_env,
):

    code = _issue(
        recovery_env,
        identity_verified=True,
        verification_method="trusted_callback",
        delivery_method="verified_voice_call",
    )

    assert isinstance(code, str)
    assert len(code) >= 32
