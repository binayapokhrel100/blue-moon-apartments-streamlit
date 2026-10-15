
"""Disposable Neon authentication integration checks.

Blue Moon Apartments — Sprint 12C.8

Default: read-only preview.
--run: temporary fictional account tests.

Never use against production or the original staging branch.
"""

import argparse
import secrets

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from sqlalchemy import delete, func, inspect, select
from sqlalchemy.orm import Session, sessionmaker

from core.security import hash_password

from database.models import (
    Base,
    AdminCredentialState,
    AdminEmployee,
    AdminRoleAssignment,
    LoginEvent,
    User,
)

from scripts.create_postgres_staging_schema import (
    create_staging_engine,
    read_staging_url,
)

from services import auth_service

from services.auth_throttle_service import (
    MAX_FAILURES,
    acquire_authentication_lock,
    clear_failed_attempts,
    get_recent_failure_count,
)


TEST_BRANCH = "auth-integration-test"
PARALLEL_FAILURES = 7


def require(condition, description):
    if not condition:
        raise RuntimeError(description)


# ==================================================
# VERIFY TARGET DATABASE
# ==================================================

def verify_target(engine, url):

    expected = {
        table.name
        for table in Base.metadata.tables.values()
    }

    with engine.connect() as conn:

        actual = set(
            inspect(conn).get_table_names(
                schema="public"
            )
        )

        user_count = conn.scalar(
            select(func.count(User.id))
        )

        database_name = conn.exec_driver_sql(
            "SELECT current_database()"
        ).scalar_one()

    require(
        actual == expected,
        "Database schema does not match application models.",
    )

    require(
        user_count == 0,
        "Existing users detected. "
        "Use a fresh isolated Neon test branch.",
    )

    print("\nNeon hostname:", url.host)
    print("Database:", database_name)
    print("Application tables:", len(actual))
    print("Existing users:", user_count)

    print(
        "Verify hostname belongs to Neon branch:",
        TEST_BRANCH,
    )

    return database_name


# ==================================================
# ISOLATED APPLICATION SESSION
# ==================================================

def make_auth_session(engine):
    """Redirect authentication calls to Neon only."""

    factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    @contextmanager
    def test_session():

        db = factory()

        try:
            yield db
            db.commit()

        except Exception:
            db.rollback()
            raise

        finally:
            db.close()

    return test_session


# ==================================================
# CREATE FICTIONAL TEST ACCOUNTS
# ==================================================

def create_test_accounts(engine):

    tag = secrets.token_hex(6)

    data = {
        "resident_email":
            f"pg-res-{tag}@example.invalid",
        "admin_email":
            f"pg-admin-{tag}@example.invalid",
        "employee_id":
            f"QA{tag.upper()}",
        "resident_password":
            secrets.token_urlsafe(20) + "Aa1!",
        "admin_password":
            secrets.token_urlsafe(20) + "Aa1!",
    }

    with Session(engine) as db:

        resident = User(
            first_name="Test",
            last_name="Resident",
            email=data["resident_email"],
            password_hash=hash_password(
                data["resident_password"]
            ),
            role="resident",
            is_active=True,
        )

        admin = User(
            first_name="Test",
            last_name="Administrator",
            email=data["admin_email"],
            password_hash=hash_password(
                data["admin_password"]
            ),
            role="admin",
            is_active=True,
        )

        db.add_all([resident, admin])
        db.flush()

        data["resident_id"] = resident.id
        data["admin_id"] = admin.id

        db.add_all([
            AdminEmployee(
                user_id=admin.id,
                employee_id=data["employee_id"],
                is_active=True,
            ),

            AdminRoleAssignment(
                user_id=admin.id,
                role="auditor",
                assigned_by=admin.id,
            ),

            AdminCredentialState(
                user_id=admin.id,
                must_change_password=False,
                credential_version=0,
            ),
        ])

        db.commit()

    return data


# ==================================================
# DATABASE INSPECTION HELPERS
# ==================================================

def failure_count(engine, flow, email):

    with Session(engine) as db:
        return get_recent_failure_count(
            db,
            flow=flow,
            identifier=email,
        )


def audit_count(engine, user_id, event_type):

    with Session(engine) as db:

        result = db.scalar(
            select(func.count(LoginEvent.id))
            .where(
                LoginEvent.user_id == user_id,
                LoginEvent.event_type == event_type,
            )
        )

        return int(result or 0)


# ==================================================
# TEST 1 — RESIDENT AUTHENTICATION
# ==================================================

def test_resident_authentication(engine, data):

    email = data["resident_email"]
    password = data["resident_password"]

    result = auth_service.authenticate_user(
        email,
        password,
    )

    require(
        result is not None
        and result.id == data["resident_id"],
        "Valid resident authentication failed.",
    )

    for _ in range(2):

        result = auth_service.authenticate_user(
            email,
            "Incorrect-Test-Password-123!",
        )

        require(
            result is None,
            "Invalid resident password was accepted.",
        )

    require(
        failure_count(engine, "resident_login", email) == 2,
        "Expected two recorded resident failures.",
    )

    result = auth_service.authenticate_user(
        email,
        password,
    )

    require(
        result is not None,
        "Valid resident login after failures was rejected.",
    )

    require(
        failure_count(engine, "resident_login", email) == 0,
        "Successful resident login did not clear failures.",
    )

    print(
        "PASS: Resident login, wrong-password rejection, "
        "and counter reset."
    )


# ==================================================
# TEST SUPPORT — ADMINISTRATOR STATUS
# ==================================================

def set_employee_active(engine, user_id, active):

    with Session(engine) as db:

        employee = db.scalar(
            select(AdminEmployee)
            .where(
                AdminEmployee.user_id == user_id
            )
        )

        require(
            employee is not None,
            "Test employee record not found.",
        )

        employee.is_active = active

        db.commit()


def set_pending_reset(engine, user_id, enabled):

    with Session(engine) as db:

        state = db.get(
            AdminCredentialState,
            user_id,
        )

        require(
            state is not None,
            "Test credential state not found.",
        )

        state.reset_token_hash = (
            secrets.token_hex(32)
            if enabled
            else None
        )

        state.reset_expires_at = (
            datetime.now(timezone.utc).replace(
                tzinfo=None
            ) + timedelta(minutes=10)
            if enabled
            else None
        )

        db.commit()


# ==================================================
# TEST 2 — ADMINISTRATOR AUTHENTICATION
# ==================================================

def test_admin_authentication(engine, data):

    email = data["admin_email"]
    employee_id = data["employee_id"]
    password = data["admin_password"]
    user_id = data["admin_id"]

    result = auth_service.authenticate_admin(
        email,
        employee_id,
        password,
    )

    require(
        result is not None
        and result.id == user_id,
        "Valid administrator login failed.",
    )

    result = auth_service.authenticate_admin(
        email,
        "INCORRECTID",
        password,
    )

    require(
        result is None,
        "Incorrect employee ID was accepted.",
    )

    require(
        auth_service.authenticate_admin(
            email,
            employee_id,
            password,
        ) is not None,
        "Valid administrator login failed.",
    )

    require(
        failure_count(engine, "admin_login", email) == 0,
        "Admin failure counter was not cleared.",
    )

    # Verify inactive employee restrictions.

    set_employee_active(engine, user_id, False)

    require(
        auth_service.authenticate_admin(
            email,
            employee_id,
            password,
        ) is None,
        "Inactive administrator was authenticated.",
    )

    set_employee_active(engine, user_id, True)

    require(
        auth_service.authenticate_admin(
            email,
            employee_id,
            password,
        ) is not None,
        "Reactivated administrator could not log in.",
    )

    # Verify pending password-reset restrictions.

    set_pending_reset(engine, user_id, True)

    require(
        auth_service.authenticate_admin(
            email,
            employee_id,
            password,
        ) is None,
        "Pending-reset administrator was authenticated.",
    )

    set_pending_reset(engine, user_id, False)

    require(
        auth_service.authenticate_admin(
            email,
            employee_id,
            password,
        ) is not None,
        "Administrator could not log in after "
        "test reset restriction was cleared.",
    )

    print(
        "PASS: Administrator authentication, employee "
        "status, and pending-reset restrictions."
    )


# ==================================================
# TEST 3 — CONCURRENT RESIDENT AUTHENTICATION
# ==================================================

def test_concurrent_login(engine, data):

    email = data["resident_email"]
    password = data["resident_password"]
    user_id = data["resident_id"]

    require(
        failure_count(
            engine,
            "resident_login",
            email,
        ) == 0,
        "Resident failure counter is not clear.",
    )

    before_failed = audit_count(
        engine,
        user_id,
        "resident_login_failed",
    )

    before_blocked = audit_count(
        engine,
        user_id,
        "resident_login_blocked",
    )

    def attempt(_):

        return auth_service.authenticate_user(
            email,
            "Bad-Password-For-Concurrency!",
        )

    with ThreadPoolExecutor(
        max_workers=PARALLEL_FAILURES
    ) as executor:

        results = list(
            executor.map(
                attempt,
                range(PARALLEL_FAILURES),
            )
        )

    require(
        all(result is None for result in results),
        "An invalid concurrent login was accepted.",
    )

    require(
        failure_count(
            engine,
            "resident_login",
            email,
        ) == MAX_FAILURES,
        "Concurrent attempts did not enforce "
        "the failure threshold.",
    )

    new_failed = (
        audit_count(
            engine,
            user_id,
            "resident_login_failed",
        ) - before_failed
    )

    new_blocked = (
        audit_count(
            engine,
            user_id,
            "resident_login_blocked",
        ) - before_blocked
    )

    require(
        new_failed == MAX_FAILURES
        and new_blocked == (
            PARALLEL_FAILURES - MAX_FAILURES
        ),
        "Concurrent security audit counts are incorrect.",
    )

    # A correct password must not bypass an active lockout.

    require(
        auth_service.authenticate_user(
            email,
            password,
        ) is None,
        "Correct password bypassed active throttling.",
    )

    # Explicit test-only clearance.
    # This is not a production recovery procedure.

    with Session(engine) as db:

        acquire_authentication_lock(db)

        clear_failed_attempts(
            db,
            flow="resident_login",
            identifier=email,
        )

        db.commit()

    require(
        auth_service.authenticate_user(
            email,
            password,
        ) is not None,
        "Valid resident login failed after "
        "test-only throttle clearance.",
    )

    print(
        f"PASS: {PARALLEL_FAILURES} concurrent attempts; "
        f"{new_failed} failures and "
        f"{new_blocked} blocked."
    )


# ==================================================
# CLEANUP — TEST ACCOUNTS ONLY
# ==================================================

def cleanup(engine, data):

    ids = [
        data["resident_id"],
        data["admin_id"],
    ]

    with Session(engine) as db:

        acquire_authentication_lock(db)

        for flow in (
            "resident_login",
            "admin_login",
            "admin_reset",
        ):

            for email in (
                data["resident_email"],
                data["admin_email"],
            ):

                clear_failed_attempts(
                    db,
                    flow=flow,
                    identifier=email,
                )

        db.execute(
            delete(LoginEvent)
            .where(LoginEvent.user_id.in_(ids))
        )

        db.execute(
            delete(AdminCredentialState)
            .where(
                AdminCredentialState.user_id.in_(ids)
            )
        )

        db.execute(
            delete(AdminRoleAssignment)
            .where(
                AdminRoleAssignment.user_id.in_(ids)
            )
        )

        db.execute(
            delete(AdminEmployee)
            .where(AdminEmployee.user_id.in_(ids))
        )

        db.execute(
            delete(User)
            .where(User.id.in_(ids))
        )

        db.commit()

    with Session(engine) as db:

        remaining = db.scalar(
            select(func.count(User.id))
            .where(User.id.in_(ids))
        )

    require(
        remaining == 0,
        "Test accounts remain in the database.",
    )

    print(
        "PASS: Temporary test accounts, login events, "
        "and failure records cleaned up."
    )


# ==================================================
# MAIN
# ==================================================

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--run",
        action="store_true",
        help="Run tests with temporary database writes.",
    )

    args = parser.parse_args()

    print("=" * 55)
    print("BLUE MOON APARTMENTS")
    print("Neon PostgreSQL Authentication Integration")
    print("=" * 55)

    url = read_staging_url()
    engine = create_staging_engine(url)

    data = None
    failed = False

    try:

        database_name = verify_target(
            engine,
            url,
        )

        if not args.run:

            print(
                "\nPREVIEW ONLY: No records created."
            )

            print(
                "\nTo run integration tests:"
            )

            print(
                "python -m "
                "scripts.check_neon_auth_integration "
                "--run"
            )

            return

        print(
            "\nWARNING: Use only the Neon branch "
            "'auth-integration-test'."
        )

        confirmation = input(
            f"Type RUN-AUTH-TEST-{database_name} "
            "to proceed: "
        ).strip()

        if confirmation != (
            f"RUN-AUTH-TEST-{database_name}"
        ):

            print(
                "Cancelled. No changes made."
            )

            return

        data = create_test_accounts(
            engine
        )

        # Temporarily route real application
        # authentication through the test engine.
        #
        # This does not change core/config.py,
        # DATABASE_URL, or the local SQLite database.

        with patch.object(
            auth_service,
            "get_db_session",
            make_auth_session(engine),
        ):

            test_resident_authentication(
                engine,
                data,
            )

            test_admin_authentication(
                engine,
                data,
            )

            test_concurrent_login(
                engine,
                data,
            )

        print(
            "\nSUCCESS: Real PostgreSQL "
            "authentication integration passed."
        )

    except Exception as exc:

        failed = True

        print(
            "\nFAILED:",
            type(exc).__name__,
        )

        if isinstance(exc, RuntimeError):
            print("Reason:", str(exc))

        print(
            "Check the isolated Neon branch "
            "before attempting another test."
        )

    finally:

        if data is not None:

            try:
                cleanup(engine, data)

            except Exception as exc:

                failed = True

                print(
                    "CLEANUP FAILED:",
                    type(exc).__name__,
                )

                print(
                    "Do not reuse this Neon branch "
                    "until it is inspected or deleted."
                )

        engine.dispose()

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
