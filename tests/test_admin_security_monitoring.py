
"""Sprint 11B.7A — Super Admin security monitoring tests."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from core.security import hash_password

from database.models import (
    AdminEmployee,
    AdminRoleChangeEvent,
    Base,
    EmergencySuperAdminRecoveryEvent,
    LoginEvent,
    User,
)

from services import (
    admin_rbac_service,
    admin_security_monitoring_service,
)

from services.auth_throttle_service import (
    record_failed_attempt,
)


# ==========================================================
# TEST CONSTANTS
# ==========================================================

NOW = datetime(2026, 10, 14, 12, 0, 0)

OWNER_EMAIL = "monitor.owner@example.test"
STAFF_EMAIL = "monitor.staff@example.test"


# ==========================================================
# TEMPORARY TEST DATABASE
# ==========================================================

@pytest.fixture()
def monitor_env(tmp_path, monkeypatch):

    db_file = (
        tmp_path / "security_monitor.sqlite"
    )

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
        admin_security_monitoring_service,
        "get_db_session",
        test_session,
    )

    monkeypatch.setattr(
        admin_rbac_service,
        "get_db_session",
        test_session,
    )

    # --------------------------------------------------
    # CREATE SUPER ADMIN
    # --------------------------------------------------

    with test_session() as db:

        owner = User(
            first_name="Monitor",
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
                employee_id="BM-MONITOR-OWNER",
                is_active=True,
            )
        )

    admin_rbac_service.bootstrap_initial_super_admin(
        OWNER_EMAIL
    )

    # --------------------------------------------------
    # CREATE REGULAR ADMINISTRATOR
    # --------------------------------------------------

    staff_id = admin_rbac_service.create_admin_employee(
        actor_id=owner_id,
        first_name="Monitor",
        last_name="Staff",
        email=STAFF_EMAIL,
        employee_id="BM-MONITOR-STAFF",
        password="StaffPassword123!",
        role="leasing_agent",
        reason="Approved monitoring dashboard fixture employee",
    )

    yield {
        "owner": owner_id,
        "staff": staff_id,
        "session": test_session,
    }

    engine.dispose()


# ==========================================================
# COMMON TEST HELPER
# ==========================================================

def _snapshot(env, **kwargs):

    return (
        admin_security_monitoring_service
        .get_admin_security_dashboard(
            env["owner"],
            now=NOW,
            **kwargs,
        )
    )


# ==========================================================
# TEST 1 — AUTHORIZED READ-ONLY ACCESS
# ==========================================================

def test_super_admin_dashboard_is_accessible_and_read_only(
    monitor_env,
):

    with monitor_env["session"]() as db:

        before = len(
            db.scalars(
                select(LoginEvent)
            ).all()
        )

    data = _snapshot(monitor_env)

    assert data["window_days"] == 7

    assert (
        data["metrics"]["failed_auth_events"]
        == 0
    )

    with monitor_env["session"]() as db:

        after = len(
            db.scalars(
                select(LoginEvent)
            ).all()
        )

    assert before == after


# ==========================================================
# TEST 2 — REGULAR ADMINISTRATOR DENIED
# ==========================================================

def test_regular_admin_cannot_see_monitoring(
    monitor_env,
):

    with pytest.raises(PermissionError):

        admin_security_monitoring_service.get_admin_security_dashboard(
            monitor_env["staff"],
            now=NOW,
        )


# ==========================================================
# TEST 3 — AUTHENTICATION METRICS
# ==========================================================

def test_failed_and_blocked_auth_event_counts(
    monitor_env,
):

    with monitor_env["session"]() as db:

        db.add_all([
            LoginEvent(
                user_id=monitor_env["staff"],
                event_type="admin_login_failed",
                success=False,
                created_at=NOW - timedelta(hours=2),
            ),
            LoginEvent(
                user_id=monitor_env["staff"],
                event_type="admin_login_blocked",
                success=False,
                created_at=NOW - timedelta(hours=1),
            ),
            LoginEvent(
                user_id=monitor_env["staff"],
                event_type="password_reset_completed",
                success=True,
                created_at=NOW - timedelta(minutes=15),
            ),
        ])

    data = _snapshot(monitor_env)

    metrics = data["metrics"]

    assert metrics["failed_auth_events"] == 2
    assert metrics["blocked_auth_events"] == 1
    assert metrics["completed_password_resets"] == 1

    assert (
        data["timeline"][0]["activity"]
        == "password_reset_completed"
    )


# ==========================================================
# TEST 4 — CURRENT ACCOUNT LOCKOUT
# ==========================================================

def test_current_lockout_is_flagged(
    monitor_env,
):

    with monitor_env["session"]() as db:

        for _ in range(5):

            record_failed_attempt(
                db,
                flow="admin_login",
                identifier=STAFF_EMAIL,
                now=NOW,
            )

    data = _snapshot(monitor_env)

    assert (
        data["metrics"]["active_admin_lockouts"]
        == 1
    )

    assert (
        data["account_flags"][0]["email"]
        == STAFF_EMAIL
    )

    assert (
        data["account_flags"][0]["status"]
        == "Temporarily locked"
    )


# ==========================================================
# TEST 5 — ROLE AUDIT AND EMERGENCY RECOVERY
# ==========================================================

def test_role_audit_and_emergency_events(
    monitor_env,
):

    with monitor_env["session"]() as db:

        db.add_all([
            AdminRoleChangeEvent(
                actor_user_id=monitor_env["owner"],
                target_user_id=monitor_env["staff"],
                previous_role="leasing_agent",
                new_role="leasing_agent",
                action="password_reset_requested",
                reason=(
                    "Employee identity independently verified"
                ),
                created_at=NOW - timedelta(minutes=12),
            ),
            EmergencySuperAdminRecoveryEvent(
                target_user_id=monitor_env["owner"],
                key_fingerprint="a" * 64,
                operator_label="trusted-operator",
                ticket_reference="INC-555",
                reason=(
                    "Emergency recovery approved by owner"
                ),
                created_at=NOW - timedelta(minutes=11),
            ),
        ])

    data = _snapshot(monitor_env)

    assert (
        data["metrics"]["password_reset_requests"]
        == 1
    )

    assert (
        data["metrics"]["emergency_resets"]
        == 1
    )

    assert any(
        row["source"] == "Emergency recovery"
        for row in data["timeline"]
    )

    # The emergency key fingerprint is not exposed.
    assert not any(
        "a" * 64 in row["details"]
        for row in data["timeline"]
    )


# ==========================================================
# TEST 6 — EVENTS OUTSIDE REPORTING WINDOW
# ==========================================================

def test_old_events_not_in_selected_window(
    monitor_env,
):

    with monitor_env["session"]() as db:

        db.add(
            LoginEvent(
                user_id=monitor_env["staff"],
                event_type="admin_login_failed",
                success=False,
                created_at=NOW - timedelta(days=40),
            )
        )

    data = _snapshot(
        monitor_env,
        days=30,
    )

    assert (
        data["metrics"]["failed_auth_events"]
        == 0
    )

    assert data["timeline"] == []


# ==========================================================
# TESTS 7–12 — INPUT VALIDATION
# ==========================================================

@pytest.mark.parametrize(
    "settings",
    [
        {"days": 0},
        {"days": 31},
        {"days": True},
        {"limit": 0},
        {"limit": 201},
        {"limit": True},
    ],
)
def test_invalid_dashboard_boundaries_rejected(
    monitor_env,
    settings,
):

    with pytest.raises(ValueError):
        _snapshot(
            monitor_env,
            **settings,
        )


# ==========================================================
# TEST 13 — TIMEZONE NORMALIZATION
# ==========================================================

def test_timezone_aware_snapshot_supported(
    monitor_env,
):

    data = (
        admin_security_monitoring_service
        .get_admin_security_dashboard(
            monitor_env["owner"],
            now=NOW.replace(
                tzinfo=timezone.utc
            ),
        )
    )

    assert data["generated_at_utc"] == NOW
