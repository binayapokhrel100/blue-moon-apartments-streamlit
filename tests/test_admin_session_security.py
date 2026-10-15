
"""Sprint 11B.3 — Administrator login and session revocation tests."""

from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core import session as core_session
from core.security import hash_password
from database.models import (
    AdminEmployee,
    AdminRoleAssignment,
    Base,
    User,
)
from services import (
    admin_rbac_service,
    auth_service,
)


PASSWORD = "SecureDemoPassword123!"
ADMIN_EMAIL = "secure.admin@example.test"
EMPLOYEE_ID = "BM-SEC-100"
RESIDENT_EMAIL = "secure.resident@example.test"


class FakeSessionState(dict):
    """Minimal Streamlit session state for isolated tests."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None

    def __setattr__(self, name, value):
        self[name] = value


@pytest.fixture()
def security_env(monkeypatch):
    """Create a temporary database and isolated Streamlit state."""

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
        auth_service,
        "get_db_session",
        test_session,
    )

    monkeypatch.setattr(
        admin_rbac_service,
        "get_db_session",
        test_session,
    )

    monkeypatch.setattr(
        core_session.st,
        "session_state",
        FakeSessionState(),
    )

    with test_session() as db:

        admin = User(
            first_name="Secure",
            last_name="Administrator",
            email=ADMIN_EMAIL,
            password_hash=hash_password(PASSWORD),
            role="admin",
            is_active=True,
        )

        resident = User(
            first_name="Secure",
            last_name="Resident",
            email=RESIDENT_EMAIL,
            password_hash=hash_password(PASSWORD),
            role="resident",
            is_active=True,
        )

        db.add_all([
            admin,
            resident,
        ])

        db.flush()

        db.add(
            AdminEmployee(
                user_id=admin.id,
                employee_id=EMPLOYEE_ID,
                is_active=True,
            )
        )

        db.add(
            AdminRoleAssignment(
                user_id=admin.id,
                role="property_manager",
                assigned_by=admin.id,
            )
        )

        ids = {
            "admin": admin.id,
            "resident": resident.id,
        }

    core_session.initialize_session()

    yield ids, test_session

    engine.dispose()


def _admin_login():
    return auth_service.authenticate_admin(
        email=ADMIN_EMAIL,
        employee_id=EMPLOYEE_ID,
        password=PASSWORD,
    )


# ==========================================================
# LOGIN ELIGIBILITY
# ==========================================================

def test_active_assigned_admin_can_log_in(
    security_env,
):
    user = _admin_login()

    assert user is not None
    assert user.role == "admin"


@pytest.mark.parametrize(
    "disabled_record",
    [
        "user",
        "employee",
    ],
)
def test_disabled_admin_cannot_log_in(
    security_env,
    disabled_record,
):
    ids, test_session = security_env

    with test_session() as db:

        if disabled_record == "user":

            user = db.get(
                User,
                ids["admin"],
            )

            user.is_active = False

        else:

            employee = db.scalar(
                select(AdminEmployee).where(
                    AdminEmployee.user_id
                    == ids["admin"]
                )
            )

            employee.is_active = False

    assert _admin_login() is None


def test_unassigned_admin_cannot_log_in(
    security_env,
):
    ids, test_session = security_env

    with test_session() as db:

        assignment = db.scalar(
            select(AdminRoleAssignment).where(
                AdminRoleAssignment.user_id
                == ids["admin"]
            )
        )

        db.delete(assignment)

    assert _admin_login() is None


@pytest.mark.parametrize(
    "employee_id, password",
    [
        (
            "WRONG-EMPLOYEE",
            PASSWORD,
        ),
        (
            EMPLOYEE_ID,
            "IncorrectPassword123!",
        ),
    ],
)
def test_wrong_credentials_cannot_log_in(
    security_env,
    employee_id,
    password,
):
    assert auth_service.authenticate_admin(
        email=ADMIN_EMAIL,
        employee_id=employee_id,
        password=password,
    ) is None


# ==========================================================
# EXISTING SESSION REVOCATION
# ==========================================================

def test_session_revoked_after_employee_deactivation(
    security_env,
):
    ids, test_session = security_env

    user = _admin_login()
    core_session.login_user(user)

    assert core_session.is_authenticated()

    with test_session() as db:

        employee = db.scalar(
            select(AdminEmployee).where(
                AdminEmployee.user_id
                == ids["admin"]
            )
        )

        employee.is_active = False

    assert core_session.is_authenticated() is False
    assert core_session.get_current_user() is None


def test_session_revoked_after_user_deactivation(
    security_env,
):
    ids, test_session = security_env

    user = _admin_login()
    core_session.login_user(user)

    assert core_session.is_authenticated()

    with test_session() as db:

        admin = db.get(
            User,
            ids["admin"],
        )

        admin.is_active = False

    assert core_session.is_authenticated() is False
    assert core_session.get_current_user() is None


def test_session_revoked_when_admin_role_removed(
    security_env,
):
    ids, test_session = security_env

    user = _admin_login()
    core_session.login_user(user)

    assert core_session.is_authenticated()

    with test_session() as db:

        assignment = db.scalar(
            select(AdminRoleAssignment).where(
                AdminRoleAssignment.user_id
                == ids["admin"]
            )
        )

        db.delete(assignment)

    assert core_session.is_authenticated() is False


# ==========================================================
# ROLE CHANGES
# ==========================================================

def test_existing_admin_session_uses_updated_role(
    security_env,
):
    ids, test_session = security_env

    user = _admin_login()
    core_session.login_user(user)

    assert core_session.is_authenticated()

    with test_session() as db:

        assignment = db.scalar(
            select(AdminRoleAssignment).where(
                AdminRoleAssignment.user_id
                == ids["admin"]
            )
        )

        assignment.role = "auditor"

    # The user remains logged in, but permissions
    # must now reflect the new database role.

    assert core_session.is_authenticated()

    current_access = (
        admin_rbac_service.get_my_admin_access(
            ids["admin"]
        )
    )

    assert current_access["role"] == "auditor"
    assert "tenants.create" not in current_access["permissions"]


# ==========================================================
# RESIDENT REGRESSION
# ==========================================================

def test_resident_session_still_works(
    security_env,
):
    user = auth_service.authenticate_user(
        RESIDENT_EMAIL,
        PASSWORD,
    )

    assert user is not None

    core_session.login_user(user)

    assert core_session.is_authenticated()

    current = core_session.get_current_user()

    assert current is not None
    assert current["role"] == "resident"


def test_cached_portal_role_change_invalidates_session(
    security_env,
):
    ids, test_session = security_env

    user = _admin_login()
    core_session.login_user(user)

    assert core_session.is_authenticated()

    with test_session() as db:

        admin = db.get(
            User,
            ids["admin"],
        )

        admin.role = "resident"

    # A cached administrator session cannot
    # silently become a resident session.

    assert core_session.is_authenticated() is False
    assert core_session.get_current_user() is None


# ==========================================================
# SPRINT 11B.4A — PASSWORD CHANGE REVOKES OLD SESSION
# ==========================================================

def test_password_change_invalidates_existing_admin_session(
    security_env,
):
    ids, _ = security_env

    user = _admin_login()

    core_session.login_user(user)

    assert core_session.is_authenticated()

    admin_rbac_service.change_own_admin_password(
        ids["admin"],
        current_password=PASSWORD,
        new_password="UpdatedPassword456!",
        confirm_password="UpdatedPassword456!",
    )

    # The old session has an outdated credential_version.

    assert core_session.is_authenticated() is False

    # The initial password can no longer authenticate.

    assert _admin_login() is None

    # The administrator can log in with the new password.

    updated = auth_service.authenticate_admin(
        email=ADMIN_EMAIL,
        employee_id=EMPLOYEE_ID,
        password="UpdatedPassword456!",
    )

    assert updated is not None
