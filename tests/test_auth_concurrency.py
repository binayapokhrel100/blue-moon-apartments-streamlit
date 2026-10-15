
"""Sprint 11B.5C.1 — atomic authentication concurrency tests."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Barrier

import pytest

from sqlalchemy import (
    create_engine,
    func,
    select,
)
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker

from core.security import hash_password

from database.models import (
    AdminEmployee,
    AdminRoleAssignment,
    AuthenticationFailureAttempt,
    Base,
    User,
)

from services import auth_service

from services.auth_throttle_service import (
    acquire_authentication_lock,
)


ADMIN_EMAIL = "atomic.admin@example.test"
RESIDENT_EMAIL = "atomic.resident@example.test"
EMPLOYEE_ID = "BM-ATOMIC-101"

PASSWORD = "AtomicPassword123!"
WRONG_PASSWORD = "DefinitelyWrong123!"


# ==========================================================
# ISOLATED FILE-BASED SQLITE FIXTURE
# ==========================================================

@pytest.fixture()
def atomic_env(tmp_path, monkeypatch):
    """
    Use a real SQLite file rather than an in-memory
    database so concurrent calls use separate
    database connections.
    """

    database_file = (
        tmp_path / "atomic_authentication.sqlite"
    )

    engine = create_engine(
        URL.create(
            "sqlite+pysqlite",
            database=str(database_file),
        ),
        connect_args={
            "check_same_thread": False,
            "timeout": 30,
        },
    )

    Base.metadata.create_all(
        engine
    )

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

    # ------------------------------------------
    # CREATE TEST ACCOUNTS
    # ------------------------------------------

    with test_session() as db:

        admin = User(
            first_name="Atomic",
            last_name="Admin",
            email=ADMIN_EMAIL,
            password_hash=hash_password(PASSWORD),
            role="admin",
            is_active=True,
        )

        resident = User(
            first_name="Atomic",
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

    yield test_session

    engine.dispose()


# ==========================================================
# FAILURE COUNT HELPER
# ==========================================================

def _failure_count(
    test_session,
    flow: str,
) -> int:

    with test_session() as db:

        count = db.scalar(
            select(
                func.count(
                    AuthenticationFailureAttempt.id
                )
            )
            .where(
                AuthenticationFailureAttempt.flow == flow
            )
        )

        return int(
            count or 0
        )


# ==========================================================
# TEST 1 — SIMULTANEOUS FAILED LOGINS
# ==========================================================

def test_simultaneous_failed_admin_logins_cannot_exceed_limit(
    atomic_env,
):

    barrier = Barrier(10)

    def attempt(_):

        barrier.wait(
            timeout=15
        )

        return auth_service.authenticate_admin(
            ADMIN_EMAIL,
            EMPLOYEE_ID,
            WRONG_PASSWORD,
        )

    with ThreadPoolExecutor(
        max_workers=10
    ) as executor:

        results = list(
            executor.map(
                attempt,
                range(10),
            )
        )

    assert all(
        user is None
        for user in results
    )

    # Ten simultaneous attempts should not record
    # ten failures. The first five failures trigger
    # the restriction, and the rest are blocked.

    assert _failure_count(
        atomic_env,
        "admin_login",
    ) == 5

    # Even the correct password is blocked once
    # the five-failure limit has been reached.

    assert auth_service.authenticate_admin(
        ADMIN_EMAIL,
        EMPLOYEE_ID,
        PASSWORD,
    ) is None


# ==========================================================
# TEST 2 — SUCCESS CLEARS PREVIOUS FAILURES
# ==========================================================

def test_four_failures_then_success_clears_counter(
    atomic_env,
):

    for _ in range(4):

        assert auth_service.authenticate_admin(
            ADMIN_EMAIL,
            EMPLOYEE_ID,
            WRONG_PASSWORD,
        ) is None

    assert _failure_count(
        atomic_env,
        "admin_login",
    ) == 4

    user = auth_service.authenticate_admin(
        ADMIN_EMAIL,
        EMPLOYEE_ID,
        PASSWORD,
    )

    assert user is not None

    assert _failure_count(
        atomic_env,
        "admin_login",
    ) == 0


# ==========================================================
# TEST 3 — ADMIN CANNOT ENTER RESIDENT PORTAL
# ==========================================================

def test_admin_credentials_cannot_enter_resident_portal(
    atomic_env,
):

    assert auth_service.authenticate_user(
        ADMIN_EMAIL,
        PASSWORD,
    ) is None

    assert _failure_count(
        atomic_env,
        "resident_login",
    ) == 1

    # The administrator can still use the proper portal.

    assert auth_service.authenticate_admin(
        ADMIN_EMAIL,
        EMPLOYEE_ID,
        PASSWORD,
    ) is not None


# ==========================================================
# TEST 4 — SEPARATE RESIDENT/ADMIN COUNTERS
# ==========================================================

def test_resident_and_admin_counters_are_independent(
    atomic_env,
):

    for _ in range(5):

        assert auth_service.authenticate_user(
            RESIDENT_EMAIL,
            WRONG_PASSWORD,
        ) is None

    assert _failure_count(
        atomic_env,
        "resident_login",
    ) == 5

    assert auth_service.authenticate_user(
        RESIDENT_EMAIL,
        PASSWORD,
    ) is None

    # Resident failures must not block unrelated
    # administrator accounts.

    assert auth_service.authenticate_admin(
        ADMIN_EMAIL,
        EMPLOYEE_ID,
        PASSWORD,
    ) is not None

    assert _failure_count(
        atomic_env,
        "admin_login",
    ) == 0


# ==========================================================
# TEST 5 — LOCK MUST BE ACQUIRED FIRST
# ==========================================================

def test_lock_requires_fresh_database_transaction(
    atomic_env,
):

    with atomic_env() as db:

        # Start a transaction by issuing a query.

        db.scalar(
            select(
                func.count(User.id)
            )
        )

        # The authentication lock must be acquired
        # before any database reads.

        with pytest.raises(
            RuntimeError,
            match="before any database query",
        ):

            acquire_authentication_lock(
                db
            )
