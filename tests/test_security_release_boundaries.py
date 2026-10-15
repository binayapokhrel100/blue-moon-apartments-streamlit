
"""Sprint 11B.8A: cross-feature security release boundaries.

This test suite creates an isolated SQLite database. It never connects
with the real application's database or invokes the emergency CLI.
"""

import ast
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from core.security import hash_password, verify_password
from database.models import (
    AdminCredentialState,
    AdminEmployee,
    AdminRoleAssignment,
    AdminRoleChangeEvent,
    Base,
    User,
)
from services import (
    admin_lockout_service,
    admin_rbac_service,
    admin_security_monitoring_service,
)


OWNER_EMAIL = "release.owner@example.test"
STAFF_EMAIL = "release.staff@example.test"
RESIDENT_EMAIL = "release.resident@example.test"

OWNER_PASSWORD = "OwnerPassword123!"
STAFF_PASSWORD = "StaffPassword123!"

REASON = (
    "Employee identity confirmed by approved "
    "in-person procedure"
)

VERIFIED = {
    "identity_verified": True,
    "verification_method": "in_person",
    "delivery_method": "in_person",
}


# ==========================================================
# ISOLATED TEST DATABASE
# ==========================================================

@pytest.fixture()
def release_env(tmp_path, monkeypatch):
    """Separate test database and authorized test identities."""

    db_path = tmp_path / "release_security.sqlite"

    engine = create_engine(
        f"sqlite+pysqlite:///{db_path.as_posix()}",
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
    def isolated_session():
        with SessionLocal() as db:
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    # Redirect service database access to the test DB.
    for module in (
        admin_rbac_service,
        admin_lockout_service,
        admin_security_monitoring_service,
    ):
        monkeypatch.setattr(
            module,
            "get_db_session",
            isolated_session,
        )

    # --------------------------------------------------
    # CREATE ADMINISTRATOR AND RESIDENT
    # --------------------------------------------------

    with isolated_session() as db:
        owner = User(
            first_name="Release",
            last_name="Owner",
            email=OWNER_EMAIL,
            password_hash=hash_password(
                OWNER_PASSWORD
            ),
            role="admin",
            is_active=True,
        )

        resident = User(
            first_name="Release",
            last_name="Resident",
            email=RESIDENT_EMAIL,
            password_hash=hash_password(
                "ResidentPassword123!"
            ),
            role="resident",
            is_active=True,
        )

        db.add_all([owner, resident])
        db.flush()

        owner_id = owner.id
        resident_id = resident.id

        db.add(
            AdminEmployee(
                user_id=owner_id,
                employee_id="BM-RELEASE-OWNER",
                is_active=True,
            )
        )

    # --------------------------------------------------
    # INITIAL SUPER ADMIN
    # --------------------------------------------------

    admin_rbac_service.bootstrap_initial_super_admin(
        OWNER_EMAIL
    )

    # --------------------------------------------------
    # REGULAR ADMINISTRATOR
    # --------------------------------------------------

    staff_id = admin_rbac_service.create_admin_employee(
        actor_id=owner_id,
        first_name="Release",
        last_name="Staff",
        email=STAFF_EMAIL,
        employee_id="BM-RELEASE-STAFF",
        password=STAFF_PASSWORD,
        role="leasing_agent",
        reason=(
            "Authorized staff account for final "
            "security regression tests"
        ),
    )

    yield {
        "owner": owner_id,
        "staff": staff_id,
        "resident": resident_id,
        "session": isolated_session,
    }

    engine.dispose()


# ==========================================================
# DIRECT SERVICE CALL HELPER
# ==========================================================

def _privileged_operation(
    name: str,
    env,
    actor_id: int,
):
    """
    Call real services directly, without Streamlit.

    A valid Super Admin is required for every action.
    """

    target = env["staff"]

    actions = {
        "directory": lambda: (
            admin_rbac_service.list_admin_role_assignments(
                actor_id
            )
        ),
        "audit": lambda: (
            admin_rbac_service.list_admin_role_audit(
                actor_id
            )
        ),
        "monitoring": lambda: (
            admin_security_monitoring_service
            .get_admin_security_dashboard(actor_id)
        ),
        "lockout_status": lambda: (
            admin_lockout_service
            .get_admin_login_lockout_status(
                actor_id,
                target,
            )
        ),
        "password_reset": lambda: (
            admin_rbac_service.request_admin_password_reset(
                actor_id=actor_id,
                target_admin_id=target,
                reason=REASON,
                **VERIFIED,
            )
        ),
    }

    return actions[name]()


# ==========================================================
# TESTS 1–5 — REGULAR ADMINISTRATOR DENIED
# ==========================================================

@pytest.mark.parametrize(
    "operation",
    [
        "directory",
        "audit",
        "monitoring",
        "lockout_status",
        "password_reset",
    ],
)
def test_regular_administrator_cannot_call_privileged_services(
    release_env,
    operation,
):
    with pytest.raises(PermissionError):
        _privileged_operation(
            operation,
            release_env,
            release_env["staff"],
        )


# ==========================================================
# TESTS 6–10 — RESIDENT DENIED
# ==========================================================

@pytest.mark.parametrize(
    "operation",
    [
        "directory",
        "audit",
        "monitoring",
        "lockout_status",
        "password_reset",
    ],
)
def test_resident_cannot_call_privileged_services(
    release_env,
    operation,
):
    with pytest.raises(PermissionError):
        _privileged_operation(
            operation,
            release_env,
            release_env["resident"],
        )


# ==========================================================
# TEST 11 — DISABLED SUPER ADMIN DENIED
# ==========================================================

def test_disabled_super_admin_cannot_access_security_monitoring(
    release_env,
):
    with release_env["session"]() as db:
        owner = db.get(
            User,
            release_env["owner"],
        )
        owner.is_active = False

    with pytest.raises(PermissionError):
        _privileged_operation(
            "monitoring",
            release_env,
            release_env["owner"],
        )

    with pytest.raises(PermissionError):
        _privileged_operation(
            "password_reset",
            release_env,
            release_env["owner"],
        )


# ==========================================================
# TEST 12 — REMOVED SUPER ADMIN ROLE DENIED
# ==========================================================

def test_removed_super_admin_role_denies_privileged_access(
    release_env,
):
    # Modify role only inside the temporary test DB.
    with release_env["session"]() as db:
        assignment = db.scalar(
            select(AdminRoleAssignment).where(
                AdminRoleAssignment.user_id
                == release_env["owner"]
            )
        )

        assignment.role = "leasing_agent"

    with pytest.raises(PermissionError):
        _privileged_operation(
            "directory",
            release_env,
            release_env["owner"],
        )

    with pytest.raises(PermissionError):
        _privileged_operation(
            "monitoring",
            release_env,
            release_env["owner"],
        )


# ==========================================================
# TESTS 13–16 — INVALID ATTESTATION REJECTED
# ==========================================================

@pytest.mark.parametrize(
    "attestation",
    [False, None, 1, "true"],
)
def test_reset_requires_literal_true_verification(
    release_env,
    attestation,
):
    with pytest.raises(
        ValueError,
        match="verification",
    ):
        admin_rbac_service.request_admin_password_reset(
            actor_id=release_env["owner"],
            target_admin_id=release_env["staff"],
            reason=REASON,
            identity_verified=attestation,
            verification_method="in_person",
            delivery_method="in_person",
        )

    # Rejected requests must leave the DB unchanged.
    with release_env["session"]() as db:
        state = db.get(
            AdminCredentialState,
            release_env["staff"],
        )

        assert state.reset_token_hash is None
        assert state.credential_version == 0

        audits = db.scalar(
            select(
                func.count(AdminRoleChangeEvent.id)
            ).where(
                AdminRoleChangeEvent.action
                == "password_reset_requested"
            )
        )

        assert audits == 0


# ==========================================================
# TEST 17 — RESIDENT CANNOT BE TARGET OF ADMIN RESET
# ==========================================================

def test_reset_rejects_resident_even_with_verified_attestation(
    release_env,
):
    with pytest.raises(PermissionError):
        admin_rbac_service.request_admin_password_reset(
            actor_id=release_env["owner"],
            target_admin_id=release_env["resident"],
            reason=REASON,
            **VERIFIED,
        )


# ==========================================================
# TEST 18 — SUPER ADMIN SELF-RESET REJECTED
# ==========================================================

def test_super_admin_cannot_issue_self_reset(
    release_env,
):
    with pytest.raises(
        ValueError,
        match="My Account",
    ):
        admin_rbac_service.request_admin_password_reset(
            actor_id=release_env["owner"],
            target_admin_id=release_env["owner"],
            reason=REASON,
            **VERIFIED,
        )


# ==========================================================
# TEST 19 — RESET CODE DOES NOT CHANGE PASSWORD/ROLE
# ==========================================================

def test_issued_code_does_not_change_password_or_role(
    release_env,
):
    code = admin_rbac_service.request_admin_password_reset(
        actor_id=release_env["owner"],
        target_admin_id=release_env["staff"],
        reason=REASON,
        **VERIFIED,
    )

    with release_env["session"]() as db:
        user = db.get(
            User,
            release_env["staff"],
        )

        state = db.get(
            AdminCredentialState,
            release_env["staff"],
        )

        role = db.scalar(
            select(AdminRoleAssignment.role).where(
                AdminRoleAssignment.user_id
                == release_env["staff"]
            )
        )

        audit = db.scalar(
            select(AdminRoleChangeEvent).where(
                AdminRoleChangeEvent.action
                == "password_reset_requested"
            )
        )

        # Issuance must not silently change credentials.
        assert verify_password(
            STAFF_PASSWORD,
            user.password_hash,
        )

        # Resetting a password must not change RBAC.
        assert role == "leasing_agent"

        # The code must be stored as a hash.
        assert state.reset_token_hash == sha256(
            code.encode("utf-8")
        ).hexdigest()

        # Existing sessions should be invalidated.
        assert state.must_change_password is True
        assert state.credential_version == 1

        # Sensitive values must not enter audit reasons.
        assert code not in audit.reason
        assert STAFF_PASSWORD not in audit.reason


# ==========================================================
# TEST 20 — OFFLINE EMERGENCY RECOVERY ISOLATION
# ==========================================================

def test_emergency_recovery_is_not_imported_by_web_entrypoints():
    """
    Ensure web entrypoints do not directly import offline
    emergency-recovery code.

    This checks direct Python imports, not dynamic imports
    or every possible runtime invocation.
    """

    root = Path(__file__).resolve().parents[1]

    app = root / "app.py"
    views_dir = root / "views"

    assert app.is_file(), "app.py is missing"
    assert views_dir.is_dir(), "views/ is missing"

    paths = [
        app,
        *views_dir.rglob("*.py"),
    ]

    for path in paths:
        tree = ast.parse(
            path.read_text(
                encoding="utf-8-sig"
            ),
            filename=str(path),
        )

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = [
                    alias.name
                    for alias in node.names
                ]

            elif isinstance(node, ast.ImportFrom):
                imported = [
                    node.module or ""
                ] + [
                    alias.name
                    for alias in node.names
                ]

            else:
                continue

            assert not any(
                item == "emergency_super_admin_service"
                or item.endswith(
                    ".emergency_super_admin_service"
                )
                or item == "emergency_super_admin_recovery"
                or item.endswith(
                    ".emergency_super_admin_recovery"
                )
                for item in imported
            ), (
                "Offline emergency recovery imported "
                f"by a web module: {path}"
            )
def test_previous_bootstrap_cannot_be_repeated_if_role_removed(
    release_env,
):
    """Historical bootstrap must remain single-use."""

    with release_env["session"]() as db:

        assignment = db.scalar(
            select(AdminRoleAssignment).where(
                AdminRoleAssignment.user_id
                == release_env["owner"]
            )
        )

        assert assignment is not None

        # Simulate accidental role-assignment deletion.
        # This occurs ONLY in the isolated test database.
        db.delete(assignment)

    with pytest.raises(
        ValueError,
        match="already been performed",
    ):
        admin_rbac_service.bootstrap_initial_super_admin(
            OWNER_EMAIL
        )