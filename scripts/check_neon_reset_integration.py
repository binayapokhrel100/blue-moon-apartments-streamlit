
"""Blue Moon Apartments: isolated PostgreSQL reset integration.

Preview:
    python -m scripts.check_neon_reset_integration

Execute:
    python -m scripts.check_neon_reset_integration --run

Use ONLY the disposable auth-integration-test Neon branch.
Never use on production or the primary staging branch.
"""

import argparse
import secrets
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from hashlib import sha256
from threading import Barrier
from unittest.mock import patch

from sqlalchemy import delete, func, inspect, or_, select
from sqlalchemy.orm import Session, sessionmaker

from core.security import hash_password, verify_password
from database.models import (
    Base,
    User,
    AdminEmployee,
    AdminRoleAssignment,
    AdminCredentialState,
    AdminRoleChangeEvent,
    LoginEvent,
    AuthenticationFailureAttempt,
)
from scripts.create_postgres_staging_schema import (
    create_staging_engine,
    read_staging_url,
)
from services import admin_rbac_service, auth_service
from services.auth_throttle_service import (
    acquire_authentication_lock,
    clear_failed_attempts,
)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def preview(engine, url):
    """Confirm schema and absence of existing auth data."""

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

        name = conn.exec_driver_sql(
            "SELECT current_database()"
        ).scalar_one()

        counts = {
            "users": conn.scalar(
                select(func.count(User.id))
            ),
            "role_audits": conn.scalar(
                select(func.count(AdminRoleChangeEvent.id))
            ),
            "login_events": conn.scalar(
                select(func.count(LoginEvent.id))
            ),
            "auth_failures": conn.scalar(
                select(func.count(AuthenticationFailureAttempt.id))
            ),
        }

    require(
        actual == expected,
        "Application tables differ from metadata.",
    )

    require(
        all(not value for value in counts.values()),
        "Existing authentication data detected. "
        "Use a fresh isolated Neon test branch.",
    )

    print("Neon hostname:", url.host)
    print("Database:", name)
    print("Application tables:", len(actual))
    print("Security tables are empty: Yes")
    print(
        "Confirm this endpoint belongs to: "
        "auth-integration-test"
    )

    return name


def make_test_session(engine):
    """Redirect application service sessions to Neon."""

    factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    @contextmanager
    def test_session():
        with factory() as db:
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    return test_session


def create_accounts(engine):
    """Create two fictional administrators for testing."""

    tag = secrets.token_hex(6)

    data = {
        "owner_email":
            f"reset-owner-{tag}@example.invalid",
        "target_email":
            f"reset-target-{tag}@example.invalid",
        "owner_employee": f"OWN{tag.upper()}",
        "target_employee": f"RST{tag.upper()}",
        "old_password":
            secrets.token_urlsafe(20) + "Aa1!",
        "new_password":
            secrets.token_urlsafe(20) + "Bb2!",
    }

    with Session(engine) as db:
        owner = User(
            first_name="Test",
            last_name="Owner",
            email=data["owner_email"],
            password_hash=hash_password(
                data["old_password"]
            ),
            role="admin",
            is_active=True,
        )

        target = User(
            first_name="Test",
            last_name="Target",
            email=data["target_email"],
            password_hash=hash_password(
                data["old_password"]
            ),
            role="admin",
            is_active=True,
        )

        db.add_all([owner, target])
        db.flush()

        data["owner_id"] = owner.id
        data["target_id"] = target.id

        # Test-only roles. Do not invoke the permanent
        # Super Admin bootstrap procedure.
        db.add_all([
            AdminEmployee(
                user_id=owner.id,
                employee_id=data["owner_employee"],
                is_active=True,
            ),
            AdminEmployee(
                user_id=target.id,
                employee_id=data["target_employee"],
                is_active=True,
            ),
            AdminRoleAssignment(
                user_id=owner.id,
                role="super_admin",
                assigned_by=owner.id,
            ),
            AdminRoleAssignment(
                user_id=target.id,
                role="leasing_agent",
                assigned_by=owner.id,
            ),
            AdminCredentialState(
                user_id=owner.id,
                must_change_password=False,
                credential_version=0,
            ),
            AdminCredentialState(
                user_id=target.id,
                must_change_password=False,
                credential_version=0,
            ),
        ])

        db.commit()

    return data


class TestState(dict):
    """Minimal Streamlit-compatible test session state."""

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key) from None

    def __setattr__(self, key, value):
        self[key] = value


def run_checks(engine, data):
    """Exercise the real PostgreSQL recovery services."""

    from core import session as session_service

    target_id = data["target_id"]
    email = data["target_email"]
    employee_id = data["target_employee"]
    old_password = data["old_password"]
    new_password = data["new_password"]

    # --------------------------------------------------
    # TEST 1 — INITIAL ADMIN LOGIN
    # --------------------------------------------------

    require(
        auth_service.authenticate_admin(
            email, employee_id, old_password
        ) is not None,
        "Initial admin login failed.",
    )

    old_version = (
        admin_rbac_service.get_my_admin_access(
            target_id
        )["credential_version"]
    )

    # --------------------------------------------------
    # TEST 2 — ISSUE ONE-TIME RESET CODE
    # --------------------------------------------------

    code = (
        admin_rbac_service.request_admin_password_reset(
            actor_id=data["owner_id"],
            target_admin_id=target_id,
            reason=(
                "Test employee identity verified "
                "for approved reset"
            ),
            identity_verified=True,
            verification_method="in_person",
            delivery_method="in_person",
        )
    )

    with Session(engine) as db:
        state = db.get(
            AdminCredentialState,
            target_id,
        )

        require(
            state.reset_token_hash
            == sha256(code.encode()).hexdigest(),
            "Reset token was not stored as a hash.",
        )

        require(
            state.reset_expires_at is not None,
            "Reset-code expiration was not saved.",
        )

        require(
            state.credential_version == old_version + 1,
            "Code issuance did not advance "
            "the credential version.",
        )

    require(
        auth_service.authenticate_admin(
            email, employee_id, old_password
        ) is None,
        "Pending reset did not block normal login.",
    )

    print(
        "PASS: Code hashing, expiration and "
        "pending-reset login restriction."
    )

    # --------------------------------------------------
    # TEST 3 — CONCURRENT SINGLE-USE REDEMPTION
    # --------------------------------------------------

    barrier = Barrier(2)

    def redeem(_):
        barrier.wait(timeout=30)

        try:
            admin_rbac_service.redeem_admin_password_reset(
                email=email,
                employee_id=employee_id,
                reset_code=code,
                new_password=new_password,
                confirm_password=new_password,
            )
            return "redeemed"

        except ValueError as exc:
            if "Invalid or expired reset code" in str(exc):
                return "rejected"
            raise

    with ThreadPoolExecutor(
        max_workers=2
    ) as pool:
        outcomes = list(
            pool.map(redeem, range(2))
        )

    require(
        outcomes.count("redeemed") == 1
        and outcomes.count("rejected") == 1,
        "Expected exactly one successful "
        f"redemption. Results: {outcomes}",
    )

    print(
        "PASS: Concurrent reset redemption "
        "accepted exactly once."
    )

    # --------------------------------------------------
    # TEST 4 — PERSISTED CREDENTIAL SECURITY
    # --------------------------------------------------

    with Session(engine) as db:
        state = db.get(
            AdminCredentialState,
            target_id,
        )

        user = db.get(
            User,
            target_id,
        )

        events = db.scalar(
            select(func.count(LoginEvent.id)).where(
                LoginEvent.user_id == target_id,
                LoginEvent.event_type
                == "password_reset_completed",
            )
        )

        require(
            state.reset_token_hash is None
            and state.reset_expires_at is None,
            "Reset code was not consumed.",
        )

        require(
            state.must_change_password is False,
            "Password reset flag was not cleared.",
        )

        require(
            state.credential_version == old_version + 2,
            "Redemption did not advance "
            "the credential version.",
        )

        require(
            verify_password(
                new_password,
                user.password_hash,
            ),
            "New password was not stored.",
        )

        require(
            not verify_password(
                old_password,
                user.password_hash,
            ),
            "Old password remains valid.",
        )

        require(
            events == 1,
            "Expected exactly one completed-reset "
            "audit event.",
        )

    require(
        auth_service.authenticate_admin(
            email, employee_id, old_password
        ) is None,
        "Old password was accepted after reset.",
    )

    require(
        auth_service.authenticate_admin(
            email, employee_id, new_password
        ) is not None,
        "New password login failed.",
    )

    print(
        "PASS: Password replacement, credential "
        "version and reset audit event."
    )

    # --------------------------------------------------
    # TEST 5 — OLD SESSION INVALIDATION
    # --------------------------------------------------

    stale = TestState(
        authenticated=True,
        user={
            "id": target_id,
            "role": "admin",
            "credential_version": old_version,
        },
        current_page="dashboard",
    )

    # Use the real session validation function, with
    # an isolated Streamlit session-state substitute.
    with (
        patch.object(
            session_service.st,
            "session_state",
            stale,
        ),
        patch.object(
            session_service,
            "get_user_by_id",
            auth_service.get_user_by_id,
        ),
        patch.object(
            session_service,
            "get_my_admin_access",
            admin_rbac_service.get_my_admin_access,
        ),
    ):
        result = session_service.get_current_user()

    require(
        result is None
        and stale["authenticated"] is False
        and stale["user"] is None,
        "Outdated administrator session was "
        "not invalidated.",
    )

    print(
        "PASS: Stale administrator session "
        "rejected after password reset."
    )


def cleanup(engine, data):
    """Remove the test accounts and related auth records."""

    ids = [
        data["owner_id"],
        data["target_id"],
    ]

    with Session(engine) as db:
        acquire_authentication_lock(db)

        for email in (
            data["owner_email"],
            data["target_email"],
        ):
            for flow in (
                "admin_login",
                "admin_reset",
            ):
                clear_failed_attempts(
                    db,
                    flow=flow,
                    identifier=email,
                )

        db.execute(
            delete(AdminRoleChangeEvent).where(
                or_(
                    AdminRoleChangeEvent.actor_user_id.in_(ids),
                    AdminRoleChangeEvent.target_user_id.in_(ids),
                )
            )
        )

        db.execute(
            delete(LoginEvent).where(
                LoginEvent.user_id.in_(ids)
            )
        )

        db.execute(
            delete(AdminRoleAssignment).where(
                AdminRoleAssignment.user_id.in_(ids)
            )
        )

        db.execute(
            delete(AdminCredentialState).where(
                AdminCredentialState.user_id.in_(ids)
            )
        )

        db.execute(
            delete(AdminEmployee).where(
                AdminEmployee.user_id.in_(ids)
            )
        )

        db.execute(
            delete(User).where(
                User.id.in_(ids)
            )
        )

        db.commit()

    with Session(engine) as db:
        remaining = db.scalar(
            select(func.count(User.id)).where(
                User.id.in_(ids)
            )
        )

    require(
        remaining == 0,
        "Temporary accounts were not removed.",
    )

    print(
        "PASS: Temporary user accounts and "
        "authentication records removed."
    )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--run",
        action="store_true",
        help="Run isolated PostgreSQL write tests.",
    )

    args = parser.parse_args()

    print("=" * 55)
    print("BLUE MOON APARTMENTS")
    print("PostgreSQL Password Recovery Integration")
    print("=" * 55)

    url = read_staging_url()
    engine = create_staging_engine(url)

    data = None
    failed = False

    try:
        database_name = preview(engine, url)

        if not args.run:
            print(
                "\nPREVIEW ONLY: Nothing changed."
            )
            return

        confirmation = input(
            f"\nType RUN-RESET-{database_name} "
            "to run test-only writes: "
        ).strip()

        if confirmation != (
            f"RUN-RESET-{database_name}"
        ):
            print(
                "Cancelled. Nothing changed."
            )
            return

        data = create_accounts(engine)
        test_session = make_test_session(engine)

        # Route the real service functions to the
        # isolated PostgreSQL engine only.
        with (
            patch.object(
                admin_rbac_service,
                "get_db_session",
                test_session,
            ),
            patch.object(
                auth_service,
                "get_db_session",
                test_session,
            ),
        ):
            run_checks(engine, data)

        print(
            "\nSUCCESS: PostgreSQL password reset "
            "and session checks passed."
        )

    except Exception as exc:
        failed = True

        print(
            "\nFAILED:",
            type(exc).__name__,
        )

        if isinstance(exc, RuntimeError):
            print("Reason:", exc)

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
                    "Do not reuse this Neon test branch "
                    "until the problem is investigated."
                )

        engine.dispose()

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
