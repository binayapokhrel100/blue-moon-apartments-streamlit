
"""Sprint 11B.4B — secure administrator password reset tests."""

from contextlib import contextmanager
from datetime import timedelta
from hashlib import sha256

import pytest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.security import hash_password, verify_password
from database.models import (
    AdminCredentialState,
    AdminEmployee,
    AdminRoleChangeEvent,
    Base,
    LoginEvent,
    User,
    utc_now,
)
from services import admin_rbac_service, auth_service


OWNER_EMAIL = "reset.owner@example.test"
TARGET_EMAIL = "reset.employee@example.test"
TARGET_EMPLOYEE_ID = "BM-RESET-101"

INITIAL_PASSWORD = "InitialPassword123!"
NEW_PASSWORD = "NewSecurePassword456!"


@pytest.fixture()
def reset_env(monkeypatch):
    """Create isolated accounts for password-reset tests."""

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
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
        admin_rbac_service,
        "get_db_session",
        test_session,
    )

    monkeypatch.setattr(
        auth_service,
        "get_db_session",
        test_session,
    )

    with test_session() as db:

        owner = User(
            first_name="Reset",
            last_name="Owner",
            email=OWNER_EMAIL,
            password_hash=hash_password(
                "OwnerSecurePassword123!"
            ),
            role="admin",
            is_active=True,
        )

        db.add(owner)
        db.flush()

        db.add(
            AdminEmployee(
                user_id=owner.id,
                employee_id="BM-OWNER-900",
                is_active=True,
            )
        )

        owner_id = owner.id

    admin_rbac_service.bootstrap_initial_super_admin(
        OWNER_EMAIL
    )

    target_id = admin_rbac_service.create_admin_employee(
        actor_id=owner_id,
        first_name="Reset",
        last_name="Employee",
        email=TARGET_EMAIL,
        employee_id=TARGET_EMPLOYEE_ID,
        password=INITIAL_PASSWORD,
        role="leasing_agent",
        reason="Approved employee for secure reset testing",
    )

    yield {
        "owner": owner_id,
        "target": target_id,
        "session": test_session,
    }

    engine.dispose()


def issue_code(reset_env):
    return admin_rbac_service.request_admin_password_reset(
        actor_id=reset_env["owner"],
        target_admin_id=reset_env["target"],
        reason="Employee identity verified for password reset",
        identity_verified=True,
        verification_method="in_person",
        delivery_method="in_person",
    )


def redeem_code(code, *, new_password=NEW_PASSWORD):
    return admin_rbac_service.redeem_admin_password_reset(
        email=TARGET_EMAIL,
        employee_id=TARGET_EMPLOYEE_ID,
        reset_code=code,
        new_password=new_password,
        confirm_password=new_password,
    )


# ==========================================================
# CODE GENERATION AND SECURE STORAGE
# ==========================================================

def test_reset_code_is_hashed_and_has_expiration(reset_env):
    code = issue_code(reset_env)

    assert isinstance(code, str)
    assert len(code) >= 40

    with reset_env["session"]() as db:
        state = db.get(
            AdminCredentialState,
            reset_env["target"],
        )

        assert state.reset_token_hash == sha256(
            code.encode("utf-8")
        ).hexdigest()

        assert state.reset_token_hash != code
        assert state.reset_expires_at > utc_now()
        assert state.credential_version >= 1

        event = db.scalar(
            select(AdminRoleChangeEvent)
            .where(
                AdminRoleChangeEvent.target_user_id
                == reset_env["target"],
                AdminRoleChangeEvent.action
                == "password_reset_requested",
            )
        )

        assert event is not None
        assert code not in event.reason


# ==========================================================
# PENDING RESET BLOCKS PASSWORD LOGIN
# ==========================================================

def test_pending_reset_blocks_normal_admin_login(reset_env):
    original_login = auth_service.authenticate_admin(
        TARGET_EMAIL,
        TARGET_EMPLOYEE_ID,
        INITIAL_PASSWORD,
    )

    assert original_login is not None

    issue_code(reset_env)

    assert auth_service.authenticate_admin(
        TARGET_EMAIL,
        TARGET_EMPLOYEE_ID,
        INITIAL_PASSWORD,
    ) is None


# ==========================================================
# SUCCESSFUL RESET AND SINGLE-USE BEHAVIOR
# ==========================================================

def test_reset_changes_password_and_consumes_code(reset_env):
    code = issue_code(reset_env)

    redeem_code(code)

    with reset_env["session"]() as db:
        state = db.get(
            AdminCredentialState,
            reset_env["target"],
        )

        user = db.get(
            User,
            reset_env["target"],
        )

        assert state.reset_token_hash is None
        assert state.reset_expires_at is None
        assert state.must_change_password is False
        assert state.credential_version >= 2

        assert verify_password(
            NEW_PASSWORD,
            user.password_hash,
        )

        assert not verify_password(
            INITIAL_PASSWORD,
            user.password_hash,
        )

        events = db.scalars(
            select(LoginEvent).where(
                LoginEvent.user_id == reset_env["target"],
                LoginEvent.event_type
                == "password_reset_completed",
            )
        ).all()

        assert len(events) == 1

    assert auth_service.authenticate_admin(
        TARGET_EMAIL,
        TARGET_EMPLOYEE_ID,
        NEW_PASSWORD,
    ) is not None

    with pytest.raises(ValueError, match="Invalid or expired"):
        redeem_code(code)


# ==========================================================
# INCORRECT OR EXPIRED CODES
# ==========================================================

def test_wrong_reset_code_is_rejected(reset_env):
    issue_code(reset_env)

    with pytest.raises(ValueError, match="Invalid or expired"):
        redeem_code("incorrect-reset-code")


def test_expired_reset_code_is_rejected(reset_env):
    code = issue_code(reset_env)

    with reset_env["session"]() as db:
        state = db.get(
            AdminCredentialState,
            reset_env["target"],
        )

        state.reset_expires_at = (
            utc_now() - timedelta(seconds=1)
        )

    with pytest.raises(ValueError, match="Invalid or expired"):
        redeem_code(code)

    # Even after expiration, the account remains
    # blocked until another valid code is issued.

    assert auth_service.authenticate_admin(
        TARGET_EMAIL,
        TARGET_EMPLOYEE_ID,
        INITIAL_PASSWORD,
    ) is None


def test_issuing_new_code_invalidates_previous_one(reset_env):
    old_code = issue_code(reset_env)
    new_code = issue_code(reset_env)

    assert old_code != new_code

    with pytest.raises(ValueError, match="Invalid or expired"):
        redeem_code(old_code)

    redeem_code(new_code)


# ==========================================================
# AUTHORIZATION
# ==========================================================

def test_non_super_admin_cannot_issue_reset(reset_env):
    with pytest.raises(
        PermissionError,
        match="Super Admin",
    ):
        admin_rbac_service.request_admin_password_reset(
            actor_id=reset_env["target"],
            target_admin_id=reset_env["owner"],
            reason="Unauthorized request to reset owner password",
        )


def test_super_admin_cannot_reset_self(reset_env):
    with pytest.raises(ValueError, match="own password"):
        admin_rbac_service.request_admin_password_reset(
            actor_id=reset_env["owner"],
            target_admin_id=reset_env["owner"],
            reason="Attempt to reset my own password using code",
        )


def test_inactive_target_cannot_receive_reset(reset_env):
    with reset_env["session"]() as db:
        employee = db.scalar(
            select(AdminEmployee).where(
                AdminEmployee.user_id
                == reset_env["target"]
            )
        )

        employee.is_active = False

    with pytest.raises(PermissionError):
        issue_code(reset_env)


# ==========================================================
# RESET CANNOT REUSE OLD PASSWORD
# ==========================================================

def test_reset_requires_a_different_password(reset_env):
    code = issue_code(reset_env)

    with pytest.raises(ValueError, match="must differ"):
        redeem_code(
            code,
            new_password=INITIAL_PASSWORD,
        )

    # Failed validation must not consume the code.
    redeem_code(code)


# ==========================================================
# TRANSACTION ROLLBACK
# ==========================================================

def test_reset_issuance_rolls_back_if_audit_fails(
    reset_env,
    monkeypatch,
):
    def fail_audit(*args, **kwargs):
        raise RuntimeError("Simulated audit failure")

    monkeypatch.setattr(
        admin_rbac_service,
        "_audit",
        fail_audit,
    )

    with pytest.raises(
        RuntimeError,
        match="Simulated audit failure",
    ):
        issue_code(reset_env)

    with reset_env["session"]() as db:
        state = db.get(
            AdminCredentialState,
            reset_env["target"],
        )

        assert state.reset_token_hash is None
        assert state.credential_version == 0


# ==========================================================
# SPRINT 11B.5B — RESET ATTEMPT RATE LIMIT TESTS
# ==========================================================

from sqlalchemy import func

from database.models import AuthenticationFailureAttempt

from services.auth_throttle_service import (
    is_attempt_allowed,
    record_failed_attempt,
)


def _reset_failure_count(reset_env) -> int:
    """Return recorded reset failures in this test database."""

    with reset_env["session"]() as db:

        count = db.scalar(
            select(
                func.count(
                    AuthenticationFailureAttempt.id
                )
            ).where(
                AuthenticationFailureAttempt.flow
                == "admin_reset"
            )
        )

        return int(count or 0)


# ==========================================================
# TEST 1 — INVALID CODE IS RECORDED
# ==========================================================

def test_invalid_reset_code_records_failure(reset_env):

    issue_code(reset_env)

    with pytest.raises(
        ValueError,
        match="Invalid or expired",
    ):
        redeem_code(
            "incorrect-reset-code"
        )

    assert _reset_failure_count(reset_env) == 1


# ==========================================================
# TEST 2 — FOUR FAILURES STILL ALLOW RESET
# ==========================================================

def test_four_invalid_codes_allow_valid_reset(reset_env):

    valid_code = issue_code(reset_env)

    for _ in range(4):

        with pytest.raises(
            ValueError,
            match="Invalid or expired",
        ):
            redeem_code(
                "incorrect-reset-code"
            )

    assert _reset_failure_count(reset_env) == 4

    # A valid code is accepted before the limit.

    redeem_code(
        valid_code
    )

    assert _reset_failure_count(reset_env) == 0


# ==========================================================
# TEST 3 — FIVE FAILURES ACTIVATE THE LIMIT
# ==========================================================

def test_five_invalid_codes_block_valid_reset(reset_env):

    valid_code = issue_code(reset_env)

    for _ in range(5):

        with pytest.raises(
            ValueError,
            match="Invalid or expired",
        ):
            redeem_code(
                "incorrect-reset-code"
            )

    assert _reset_failure_count(reset_env) == 5

    # Even the correct code is now temporarily blocked.

    with pytest.raises(
        ValueError,
        match="Invalid or expired",
    ):
        redeem_code(
            valid_code
        )

    # A blocked attempt is not recorded again.

    assert _reset_failure_count(reset_env) == 5


# ==========================================================
# TEST 4 — REISSUING A CODE CLEARS OLD FAILURES
# ==========================================================

def test_new_reset_code_clears_old_failures(reset_env):

    old_code = issue_code(reset_env)

    for _ in range(5):

        with pytest.raises(
            ValueError,
            match="Invalid or expired",
        ):
            redeem_code(
                "incorrect-reset-code"
            )

    assert _reset_failure_count(reset_env) == 5

    # Super Admin issues a replacement reset.

    new_code = issue_code(reset_env)

    assert old_code != new_code

    assert _reset_failure_count(reset_env) == 0

    # The replacement code must work.

    redeem_code(
        new_code
    )

    assert _reset_failure_count(reset_env) == 0


# ==========================================================
# TEST 5 — PASSWORD POLICY ERRORS DO NOT COUNT
# ==========================================================

def test_invalid_new_password_does_not_count_as_code_failure(
    reset_env,
):

    valid_code = issue_code(reset_env)

    with pytest.raises(ValueError):

        redeem_code(
            valid_code,
            new_password="short",
        )

    assert _reset_failure_count(reset_env) == 0

    # A password-policy error must not consume
    # the valid reset code.

    redeem_code(
        valid_code
    )

    assert _reset_failure_count(reset_env) == 0


# ==========================================================
# TEST 6 — EXPIRED CODE COUNTS AS A FAILURE
# ==========================================================

def test_expired_reset_code_records_failure(reset_env):

    code = issue_code(reset_env)

    with reset_env["session"]() as db:

        state = db.get(
            AdminCredentialState,
            reset_env["target"],
        )

        state.reset_expires_at = (
            utc_now()
            - timedelta(seconds=1)
        )

    with pytest.raises(
        ValueError,
        match="Invalid or expired",
    ):
        redeem_code(
            code
        )

    assert _reset_failure_count(reset_env) == 1


# ==========================================================
# TEST 7 — RESET AND LOGIN COUNTERS ARE INDEPENDENT
# ==========================================================

def test_reset_failures_do_not_affect_login_counter(reset_env):

    issue_code(reset_env)

    for _ in range(5):

        with pytest.raises(
            ValueError,
            match="Invalid or expired",
        ):
            redeem_code(
                "incorrect-reset-code"
            )

    with reset_env["session"]() as db:

        # The reset flow is restricted.

        assert not is_attempt_allowed(
            db,
            flow="admin_reset",
            identifier=TARGET_EMAIL,
        )

        # The login rate-limit counter is separate.
        # Note: normal password login is still blocked
        # by the pending-reset credential state.

        assert is_attempt_allowed(
            db,
            flow="admin_login",
            identifier=TARGET_EMAIL,
        )


# ==========================================================
# TEST 8 — FAILED LOGIN RECORDS SURVIVE RESET ISSUANCE
# ==========================================================

def test_new_reset_code_does_not_clear_login_failures(
    reset_env,
):

    with reset_env["session"]() as db:

        for _ in range(3):

            record_failed_attempt(
                db,
                flow="admin_login",
                identifier=TARGET_EMAIL,
            )

    # Issue a reset and record incorrect codes.

    issue_code(reset_env)

    with pytest.raises(
        ValueError,
        match="Invalid or expired",
    ):
        redeem_code(
            "incorrect-reset-code"
        )

    # Reissue a reset. Only reset-code failures
    # should be cleared.

    issue_code(reset_env)

    with reset_env["session"]() as db:

        login_count = db.scalar(
            select(
                func.count(
                    AuthenticationFailureAttempt.id
                )
            ).where(
                AuthenticationFailureAttempt.flow
                == "admin_login"
            )
        )

        assert login_count == 3

    assert _reset_failure_count(reset_env) == 0
