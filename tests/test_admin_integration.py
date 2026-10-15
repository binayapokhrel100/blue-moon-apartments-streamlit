
"""Sprint 09 — Admin security and integration tests.

All tests use an isolated, temporary in-memory SQLite database.
The real Blue Moon application database is never modified.
"""

from contextlib import contextmanager
from database.models import AdminRoleAssignment
from services import admin_tenant_history_service
from services import admin_apartment_availability_service
from services import admin_deposit_settlement_service
from services import admin_apartment_transfer_service
from services import admin_lease_renewal_service
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from services import admin_tenancy_service
from database.models import MoveOutInspection
from services import admin_moveout_inspection_service

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from services import admin_deposit_settlement_service
from database.models import (
    DepositSettlement,
    DepositDeduction,
    DepositSettlementEvent,
)

from database.models import (
    AdminEmployee,
    Announcement,
    Apartment,
    ApartmentTransfer,
    CommunityNews,
    Lease,
    MaintenanceRequest,
    MaintenanceUpdate,
    Notification,
    Payment,
    LeaseRenewal,
    TenancyEvent,
    User,
)

from core.security import verify_password

from services import admin_content_service
from services import admin_management_service
from services import admin_operations_service
from services import announcement_service
from services import community_news_service


# ==========================================================
# ISOLATED DATABASE FIXTURE
# ==========================================================

@pytest.fixture
def admin_env(monkeypatch):
    """
    Create a fresh SQLite database for each test.

    Redirect all admin and resident content services
    to the test database, never the application's
    actual database.
    """

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={
            "check_same_thread": False,
        },
        poolclass=StaticPool,
    )

    # Create all tables using existing SQLAlchemy models.
    User.__table__.metadata.create_all(engine)

    TestingSession = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    @contextmanager
    def test_session():
        with TestingSession() as db:
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    # Redirect every relevant service to the test DB.

    for module in (
        admin_content_service,
        admin_management_service,
        admin_operations_service,
        admin_tenancy_service,
        admin_lease_renewal_service,
        admin_apartment_transfer_service,
        admin_moveout_inspection_service,
        admin_deposit_settlement_service,
        admin_apartment_availability_service,
        admin_tenant_history_service,
        announcement_service,
        community_news_service,
    ):
        monkeypatch.setattr(
            module,
            "get_db_session",
            test_session,
            admin_tenant_history_service,

        )

    # ------------------------------------------------------
    # SEED A TEST APARTMENT, ADMIN AND RESIDENT
    # ------------------------------------------------------

    with test_session() as db:

        apartment = Apartment(
            unit_number="QA-101",
            floor=1,
            bedrooms=1,
            bathrooms=Decimal("1.0"),
            monthly_rent=Decimal("1450.00"),
            is_occupied=True,
        )

        db.add(apartment)
        db.flush()

        administrator = User(
            first_name="Test",
            last_name="Administrator",
            email="qa-admin@example.com",
            password_hash="test-fixture-only",
            role="admin",
            is_active=True,
        )

        resident = User(
            first_name="Test",
            last_name="Resident",
            email="qa-resident@example.com",
            password_hash="test-fixture-only",
            role="resident",
            is_active=True,
            apartment_id=apartment.id,
        )

        db.add_all(
            [
                administrator,
                resident,
            ]
        )

        db.flush()

        employee = AdminEmployee(
            user_id=administrator.id,
            employee_id="QA-EMP-001",
            is_active=True,
        )

        db.add(employee)
        db.flush()

        ids = {
            "admin_id": administrator.id,
            "resident_id": resident.id,
            "apartment_id": apartment.id,
            "employee_id": employee.id,
        }

    yield {
        **ids,
        "session": test_session,
    }

    engine.dispose()


# ==========================================================
# HELPER: ANNOUNCEMENT
# ==========================================================

def _create_announcement(
    env,
    *,
    published=False,
    title="Elevator Maintenance",
):
    return admin_content_service.create_admin_announcement(
        env["admin_id"],
        title=title,
        message=(
            "The elevator will be inspected "
            "during the scheduled maintenance window."
        ),
        category="Maintenance",
        priority="Normal",
        expires_on="",
        published=published,
    )


# ==========================================================
# HELPER: COMMUNITY NEWS
# ==========================================================

def _create_news(
    env,
    *,
    active=False,
    title="Community Event Update",
):
    return admin_content_service.create_admin_community_news(
        env["admin_id"],
        title=title,
        summary=(
            "Residents are invited to participate "
            "in the upcoming community event."
        ),
        category="Community",
        source_name="Blue Moon Management",
        source_url="",
        active=active,
    )


# ==========================================================
# TEST 1 — RESIDENT CANNOT USE ADMIN SERVICES
# ==========================================================

def test_resident_cannot_perform_admin_actions(admin_env):

    resident_id = admin_env["resident_id"]

    with pytest.raises(PermissionError):

        admin_management_service.create_apartment(
            resident_id,
            unit_number="QA-201",
            floor=2,
            bedrooms=2,
            bathrooms=2.0,
            monthly_rent=1800,
        )

    with pytest.raises(PermissionError):

        admin_content_service.create_admin_announcement(
            resident_id,
            title="Unauthorized Notice",
            message="This action must be rejected.",
            category="General",
            priority="Normal",
            expires_on="",
            published=True,
        )

    with pytest.raises(PermissionError):

        admin_operations_service.get_admin_payments(
            resident_id
        )


# ==========================================================
# TEST 2 — INACTIVE ADMIN EMPLOYEE IS BLOCKED
# ==========================================================

def test_inactive_admin_employee_rejected(admin_env):

    with admin_env["session"]() as db:

        employee = db.get(
            AdminEmployee,
            admin_env["employee_id"],
        )

        employee.is_active = False

    with pytest.raises(PermissionError):

        admin_content_service.get_admin_announcements(
            admin_env["admin_id"]
        )


# ==========================================================
# TEST 3 — DRAFT, PUBLISH AND UNPUBLISH
# ==========================================================

def test_announcement_draft_publish_unpublish(admin_env):

    announcement_id = _create_announcement(
        admin_env,
        published=False,
    )

    # Draft must not be visible.
    visible = announcement_service.get_active_announcements()

    assert not any(
        item["id"] == announcement_id
        for item in visible
    )

    # Publish the draft.
    admin_content_service.update_admin_announcement(
        admin_env["admin_id"],
        announcement_id,
        title="Elevator Maintenance",
        message=(
            "The elevator will be inspected "
            "during the scheduled maintenance window."
        ),
        category="Maintenance",
        priority="Normal",
        expires_on="",
        published=True,
    )

    visible = announcement_service.get_active_announcements()

    assert any(
        item["id"] == announcement_id
        for item in visible
    )

    # Unpublish again.
    admin_content_service.update_admin_announcement(
        admin_env["admin_id"],
        announcement_id,
        title="Elevator Maintenance",
        message=(
            "The elevator will be inspected "
            "during the scheduled maintenance window."
        ),
        category="Maintenance",
        priority="Normal",
        expires_on="",
        published=False,
    )

    visible = announcement_service.get_active_announcements()

    assert not any(
        item["id"] == announcement_id
        for item in visible
    )


# ==========================================================
# TEST 4 — EXPIRED ANNOUNCEMENT IS HIDDEN
# ==========================================================

def test_expired_announcement_is_hidden(admin_env):

    announcement_id = _create_announcement(
        admin_env,
        published=True,
    )

    with admin_env["session"]() as db:

        announcement = db.get(
            Announcement,
            announcement_id,
        )

        announcement.expires_at = (
            datetime.now(timezone.utc)
            - timedelta(days=1)
        ).replace(tzinfo=None)

    visible = announcement_service.get_active_announcements()

    assert not any(
        item["id"] == announcement_id
        for item in visible
    )


# ==========================================================
# TEST 5 — FUTURE ANNOUNCEMENT IS HIDDEN
# ==========================================================

def test_future_announcement_is_hidden(admin_env):

    announcement_id = _create_announcement(
        admin_env,
        published=True,
    )

    with admin_env["session"]() as db:

        announcement = db.get(
            Announcement,
            announcement_id,
        )

        announcement.published_at = (
            datetime.now(timezone.utc)
            + timedelta(days=1)
        ).replace(tzinfo=None)

    visible = announcement_service.get_active_announcements()

    assert not any(
        item["id"] == announcement_id
        for item in visible
    )


# ==========================================================
# TEST 6 — HIDDEN NEWS IS NOT VISIBLE
# ==========================================================

def test_hidden_community_news_is_not_visible(admin_env):

    news_id = _create_news(
        admin_env,
        active=False,
    )

    visible = community_news_service.get_active_community_news()

    assert not any(
        item["id"] == news_id
        for item in visible
    )

    # Activate the news.
    admin_content_service.update_admin_community_news(
        admin_env["admin_id"],
        news_id,
        title="Community Event Update",
        summary=(
            "Residents are invited to participate "
            "in the upcoming community event."
        ),
        category="Community",
        source_name="Blue Moon Management",
        source_url="",
        active=True,
    )

    visible = community_news_service.get_active_community_news()

    assert any(
        item["id"] == news_id
        for item in visible
    )

    # Hide the news again.
    admin_content_service.update_admin_community_news(
        admin_env["admin_id"],
        news_id,
        title="Community Event Update",
        summary=(
            "Residents are invited to participate "
            "in the upcoming community event."
        ),
        category="Community",
        source_name="Blue Moon Management",
        source_url="",
        active=False,
    )

    visible = community_news_service.get_active_community_news()

    assert not any(
        item["id"] == news_id
        for item in visible
    )


# ==========================================================
# TEST 7 — FUTURE COMMUNITY NEWS IS HIDDEN
# ==========================================================

def test_future_community_news_is_hidden(admin_env):

    news_id = _create_news(
        admin_env,
        active=True,
    )

    with admin_env["session"]() as db:

        news = db.get(
            CommunityNews,
            news_id,
        )

        news.published_at = (
            datetime.now(timezone.utc)
            + timedelta(days=1)
        ).replace(tzinfo=None)

    visible = community_news_service.get_active_community_news()

    assert not any(
        item["id"] == news_id
        for item in visible
    )


# ==========================================================
# TEST 8 — DUPLICATE APARTMENT IS REJECTED
# ==========================================================

def test_duplicate_apartment_rejected(admin_env):

    with pytest.raises(
        ValueError,
        match="already exists",
    ):

        admin_management_service.create_apartment(
            admin_env["admin_id"],
            unit_number="qa-101",
            floor=1,
            bedrooms=1,
            bathrooms=1.0,
            monthly_rent=1450,
        )


# ==========================================================
# TEST 9 — RESIDENT PASSWORD IS HASHED
# ==========================================================


def test_create_resident_hashes_password(admin_env):

    admin_id = admin_env["admin_id"]
    password = "TemporaryPassword123!"

    apartment_id = admin_management_service.create_apartment(
        admin_id,
        unit_number="QA-301",
        floor=3,
        bedrooms=1,
        bathrooms=1.0,
        monthly_rent=1600,
    )

    resident_id = admin_management_service.create_resident(
        admin_id,
        first_name="Jordan",
        last_name="Taylor",
        email="jordan.qa@example.com",
        password=password,
        phone="5551234567",
        apartment_id=apartment_id,
        lease_start=date.today(),
        lease_end=(
            date.today()
            + timedelta(days=365)
        ),
    )

    with admin_env["session"]() as db:

        resident = db.get(User, resident_id)

        assert resident is not None
        assert resident.role == "resident"
        assert resident.is_active is True
        assert resident.apartment_id == apartment_id
        assert resident.password_hash != password

        assert verify_password(
            password,
            resident.password_hash,
        )

        lease = db.scalar(
            select(Lease).where(
                Lease.resident_id == resident_id
            )
        )

        assert lease is not None
        assert lease.status == "active"
        assert lease.apartment_id == apartment_id
        assert lease.monthly_rent == Decimal("1600.00")


# ==========================================================
# TEST 10 — DUPLICATE EMAIL IS REJECTED
# ==========================================================

def test_duplicate_resident_email_rejected(admin_env):

    today = date.today()

    with pytest.raises(
        ValueError,
        match="already registered",
    ):

        admin_management_service.create_resident(
            admin_env["admin_id"],
            first_name="Another",
            last_name="Resident",
            email="QA-RESIDENT@example.com",
            password="TemporaryPassword123!",
            apartment_id=admin_env["apartment_id"],
            lease_start=today,
            lease_end=today + timedelta(days=365),
        )


# ==========================================================
# TEST 11 — APARTMENT OCCUPANCY UPDATES
# ==========================================================


def test_apartment_occupancy_updates(admin_env):

    admin_id = admin_env["admin_id"]
    today = date.today()

    # Create a vacant apartment.

    apartment_id = admin_management_service.create_apartment(
        admin_id,
        unit_number="QA-202",
        floor=2,
        bedrooms=2,
        bathrooms=1.5,
        monthly_rent=1750,
    )

    with admin_env["session"]() as db:
        apartment = db.get(Apartment, apartment_id)
        assert apartment.is_occupied is False

    # Add a resident with an active lease.

    resident_id = admin_management_service.create_resident(
        admin_id,
        first_name="Morgan",
        last_name="Parker",
        email="morgan.qa@example.com",
        password="TemporaryPassword123!",
        apartment_id=apartment_id,
        lease_start=today,
        lease_end=today + timedelta(days=365),
    )

    # Apartment should now be occupied.

    with admin_env["session"]() as db:
        apartment = db.get(Apartment, apartment_id)
        assert apartment.is_occupied is True

    # An active lease prevents unassignment.

    with pytest.raises(
        ValueError,
        match="active lease",
    ):
        admin_management_service.update_resident(
            admin_id,
            resident_id,
            first_name="Morgan",
            last_name="Parker",
            email="morgan.qa@example.com",
            phone="",
            apartment_id=None,
            is_active=True,
        )

    # The failed update must preserve the assignment.

    with admin_env["session"]() as db:
        resident = db.get(User, resident_id)
        apartment = db.get(Apartment, apartment_id)

        assert resident.apartment_id == apartment_id
        assert apartment.is_occupied is True


# ==========================================================
# HELPER — CREATE MAINTENANCE REQUEST
# ==========================================================

def _create_maintenance_request(env):

    with env["session"]() as db:

        request = MaintenanceRequest(
            request_number="MR-QA-1001",
            resident_id=env["resident_id"],
            apartment_id=env["apartment_id"],
            category="Plumbing",
            location_detail="Kitchen",
            description=(
                "The kitchen faucet is leaking "
                "and needs to be repaired."
            ),
            urgency="High",
            status="Submitted",
        )

        db.add(request)
        db.flush()

        return request.id


# ==========================================================
# TEST 12 — MAINTENANCE UPDATE AND NOTIFICATION
# ==========================================================

def test_maintenance_update_creates_notification(admin_env):

    request_id = _create_maintenance_request(
        admin_env
    )

    admin_operations_service.update_maintenance_request(
        admin_env["admin_id"],
        request_id,
        expected_status="Submitted",
        new_status="In Progress",
        technician_name="Alex Technician",
        note="A technician has started the repair.",
    )

    with admin_env["session"]() as db:

        request = db.get(
            MaintenanceRequest,
            request_id,
        )

        assert request.status == "In Progress"
        assert request.technician_name == "Alex Technician"

        updates = db.scalars(
            select(MaintenanceUpdate).where(
                MaintenanceUpdate.request_id == request_id
            )
        ).all()

        assert len(updates) == 1
        assert updates[0].status == "In Progress"

        notifications = db.scalars(
            select(Notification).where(
                Notification.user_id
                == admin_env["resident_id"],
                Notification.notification_type
                == "maintenance",
            )
        ).all()

        assert len(notifications) == 1
        assert notifications[0].is_read is False


# ==========================================================
# TEST 13 — INVALID STATUS TRANSITION REJECTED
# ==========================================================

def test_invalid_maintenance_transition_rejected(admin_env):

    request_id = _create_maintenance_request(
        admin_env
    )

    with pytest.raises(
        ValueError,
        match="Cannot change status",
    ):

        admin_operations_service.update_maintenance_request(
            admin_env["admin_id"],
            request_id,
            expected_status="Submitted",
            new_status="Completed",
            technician_name="Alex Technician",
            note="Trying to skip required work stages.",
        )

    # Verify the failed operation did not change the DB.
    with admin_env["session"]() as db:

        request = db.get(
            MaintenanceRequest,
            request_id,
        )

        assert request.status == "Submitted"


# ==========================================================
# TEST 14 — ADMIN PAYMENT REPORT INITIAL STATE
# ==========================================================

def test_admin_payment_reporting(admin_env):

    report = admin_operations_service.get_admin_payments(
        admin_env["admin_id"]
    )

    assert report["total_records"] == 0
    assert report["confirmed_records"] == 0
    assert Decimal(
        str(report["confirmed_total"])
    ) == Decimal("0.00")
    assert report["payments"] == []


def test_new_resident_requires_apartment(admin_env):

    today = date.today()

    with pytest.raises(
        ValueError,
        match="Apartment assignment is required",
    ):
        admin_management_service.create_resident(
            admin_env["admin_id"],
            first_name="Required",
            last_name="Apartment",
            email="required.unit@example.com",
            password="TemporaryPassword123!",
            apartment_id=None,
            lease_start=today,
            lease_end=today + timedelta(days=365),
        )


# ==========================================================
# TEST — REJECT ALREADY OCCUPIED APARTMENT
# ==========================================================

def test_edit_resident_rejects_occupied_apartment(admin_env):

    admin_id = admin_env["admin_id"]
    original_apartment_id = admin_env["apartment_id"]
    resident_id = admin_env["resident_id"]

    # Create another apartment and occupy it
    # with a different resident.

    occupied_id = admin_management_service.create_apartment(
        admin_id,
        unit_number="QA-401",
        floor=4,
        bedrooms=2,
        bathrooms=2.0,
        monthly_rent=1900,
    )

    today = date.today()

    new_resident_id = admin_management_service.create_resident(
        admin_id,
        first_name="Other",
        last_name="Resident",
        email="other.occupied@example.com",
        password="TemporaryPassword123!",
        apartment_id=occupied_id,
        lease_start=today,
        lease_end=today + timedelta(days=365),
    )

    # Original resident must not move to
    # the other resident's occupied unit.

    with pytest.raises(
        ValueError,
        match="already occupied",
    ):
        admin_management_service.update_resident(
            admin_id,
            resident_id,
            first_name="Test",
            last_name="Resident",
            email="qa-resident@example.com",
            phone="",
            apartment_id=occupied_id,
            is_active=True,
        )

    with admin_env["session"]() as db:

        original = db.get(User, resident_id)
        other = db.get(User, new_resident_id)

        assert original.apartment_id == original_apartment_id
        assert other.apartment_id == occupied_id


# ==========================================================
# TEST — ALLOW EDITING RESIDENT'S OWN OCCUPIED UNIT
# ==========================================================

def test_edit_resident_can_keep_current_apartment(admin_env):

    admin_id = admin_env["admin_id"]
    resident_id = admin_env["resident_id"]

    admin_management_service.update_resident(
        admin_id,
        resident_id,
        first_name="Updated",
        last_name="Resident",
        email="qa-resident@example.com",
        phone="5551234567",
        apartment_id=admin_env["apartment_id"],
        is_active=True,
    )

    with admin_env["session"]() as db:

        resident = db.get(User, resident_id)

        assert resident.first_name == "Updated"
        assert resident.phone == "5551234567"
        assert resident.apartment_id == admin_env["apartment_id"]


# ==========================================================
# TEST — DETECT ASSIGNMENT WHEN OCCUPANCY FLAG IS WRONG
# ==========================================================

def test_edit_resident_detects_stale_occupancy(admin_env):

    admin_id = admin_env["admin_id"]

    apartment_id = admin_management_service.create_apartment(
        admin_id,
        unit_number="QA-402",
        floor=4,
        bedrooms=1,
        bathrooms=1.0,
        monthly_rent=1500,
    )

    # Simulate old/inconsistent data:
    # apartment flag says vacant, but another
    # inactive resident is still assigned to it.

    with admin_env["session"]() as db:

        other = User(
            first_name="Inactive",
            last_name="Resident",
            email="inactive.assignment@example.com",
            password_hash="test-fixture-only",
            role="resident",
            is_active=False,
            apartment_id=apartment_id,
        )

        db.add(other)

    with pytest.raises(
        ValueError,
        match="already assigned",
    ):
        admin_management_service.update_resident(
            admin_id,
            admin_env["resident_id"],
            first_name="Test",
            last_name="Resident",
            email="qa-resident@example.com",
            phone="",
            apartment_id=apartment_id,
            is_active=True,
        )

    # Assignment must remain unchanged.

    with admin_env["session"]() as db:

        resident = db.get(
            User,
            admin_env["resident_id"],
        )

        apartment = db.get(
            Apartment,
            apartment_id,
        )

        assert resident.apartment_id == admin_env["apartment_id"]
        assert apartment.is_occupied is False


# ==========================================================
# TENANCY TEST HELPERS
# ==========================================================

def _create_moveout_resident(admin_env):
    """Create a leaseholder in a new vacant test apartment."""

    admin_id = admin_env["admin_id"]
    today = date.today()

    apartment_id = admin_management_service.create_apartment(
        admin_id,
        unit_number="QA-MOVEOUT",
        floor=2,
        bedrooms=1,
        bathrooms=1.0,
        monthly_rent=1500,
    )

    resident_id = admin_management_service.create_resident(
        admin_id,
        first_name="Moveout",
        last_name="Resident",
        email="moveout.qa@example.com",
        password="TemporaryPassword123!",
        apartment_id=apartment_id,
        lease_start=today,
        lease_end=today + timedelta(days=365),
        security_deposit=500,
    )

    return resident_id, apartment_id


# ==========================================================
# TEST 1 — TERMINATION RELEASES APARTMENT
# ==========================================================

def test_lease_termination_releases_apartment(admin_env):

    resident_id, apartment_id = _create_moveout_resident(
        admin_env
    )

    # Add financial history that must survive termination.
    with admin_env["session"]() as db:
        db.add(
            Payment(
                resident_id=resident_id,
                amount=Decimal("1500.00"),
                payment_month=date.today().replace(day=1),
                payment_method="Bank Transfer",
                status="confirmed",
                confirmation_number="QA-MOVEOUT-PAYMENT-001",
            )
        )

    admin_tenancy_service.terminate_lease_and_move_out(
        admin_env["admin_id"],
        resident_id,
        reason="Resident requested early lease termination.",
    )

    with admin_env["session"]() as db:

        resident = db.get(User, resident_id)
        apartment = db.get(Apartment, apartment_id)

        lease = db.scalar(
            select(Lease).where(
                Lease.resident_id == resident_id
            )
        )

        payment = db.scalar(
            select(Payment).where(
                Payment.resident_id == resident_id
            )
        )

        event = db.scalar(
            select(TenancyEvent).where(
                TenancyEvent.resident_id == resident_id
            )
        )

        assert resident is not None
        assert resident.is_active is False
        assert resident.apartment_id is None

        assert apartment.is_occupied is False

        assert lease is not None
        assert lease.status == "terminated"
        assert lease.end_date == (
            date.today() + timedelta(days=365)
        )

        assert payment is not None
        assert payment.amount == Decimal("1500.00")

        assert event is not None
        assert event.event_type == "lease_terminated"
        assert event.lease_id == lease.id


# ==========================================================
# TEST 2 — ARCHIVE TENANT WITHOUT ACTIVE LEASE
# ==========================================================

def test_archive_resident_preserves_account(admin_env):

    resident_id = admin_env["resident_id"]
    apartment_id = admin_env["apartment_id"]

    admin_tenancy_service.archive_resident(
        admin_env["admin_id"],
        resident_id,
        reason="Resident account no longer required.",
    )

    with admin_env["session"]() as db:

        resident = db.get(User, resident_id)
        apartment = db.get(Apartment, apartment_id)

        assert resident is not None
        assert resident.is_active is False
        assert resident.apartment_id is None

        assert apartment.is_occupied is False

        event = db.scalar(
            select(TenancyEvent).where(
                TenancyEvent.resident_id == resident_id
            )
        )

        assert event is not None
        assert event.event_type == "account_archived"


# ==========================================================
# TEST 3 — CANNOT ARCHIVE ACTIVE LEASEHOLDER
# ==========================================================

def test_archive_rejects_active_lease(admin_env):

    resident_id, apartment_id = _create_moveout_resident(
        admin_env
    )

    with pytest.raises(
        ValueError,
        match="active lease",
    ):
        admin_tenancy_service.archive_resident(
            admin_env["admin_id"],
            resident_id,
            reason="Attempting to skip lease termination.",
        )

    with admin_env["session"]() as db:

        resident = db.get(User, resident_id)
        apartment = db.get(Apartment, apartment_id)

        assert resident.is_active is True
        assert resident.apartment_id == apartment_id
        assert apartment.is_occupied is True


# ==========================================================
# TEST 4 — RESIDENT CANNOT ARCHIVE OR TERMINATE
# ==========================================================

def test_resident_cannot_perform_moveout_actions(admin_env):

    unauthorized_id = admin_env["resident_id"]

    with pytest.raises(PermissionError):
        admin_tenancy_service.archive_resident(
            unauthorized_id,
            unauthorized_id,
            reason="Unauthorized attempt to archive account.",
        )

    with pytest.raises(PermissionError):
        admin_tenancy_service.terminate_lease_and_move_out(
            unauthorized_id,
            unauthorized_id,
            reason="Unauthorized attempt to end a lease.",
        )


# ==========================================================
# TEST 5 — CANNOT TERMINATE THE SAME LEASE TWICE
# ==========================================================

def test_lease_cannot_be_terminated_twice(admin_env):

    resident_id, _ = _create_moveout_resident(
        admin_env
    )

    admin_tenancy_service.terminate_lease_and_move_out(
        admin_env["admin_id"],
        resident_id,
        reason="Early move-out requested by resident.",
    )

    with pytest.raises(ValueError):
        admin_tenancy_service.terminate_lease_and_move_out(
            admin_env["admin_id"],
            resident_id,
            reason="Attempting a second lease termination.",
        )

    with admin_env["session"]() as db:

        events = db.scalars(
            select(TenancyEvent).where(
                TenancyEvent.resident_id == resident_id,
                TenancyEvent.event_type == "lease_terminated",
            )
        ).all()

        assert len(events) == 1



# ==========================================================
# LEASE RENEWAL TEST HELPERS
# ==========================================================

def _create_renewal_test_lease(admin_env):
    """Create a resident and return the current active lease."""

    resident_id, apartment_id = _create_moveout_resident(
        admin_env
    )

    with admin_env["session"]() as db:

        lease = db.scalar(
            select(Lease).where(
                Lease.resident_id == resident_id
            )
        )

        assert lease is not None

        return (
            resident_id,
            apartment_id,
            lease.id,
            lease.end_date,
        )


# ==========================================================
# TEST 1 — EXTEND LEASE AND RECORD HISTORY
# ==========================================================

def test_lease_renewal_updates_date_and_history(admin_env):

    resident_id, apartment_id, lease_id, old_end = (
        _create_renewal_test_lease(admin_env)
    )

    new_end = old_end + timedelta(days=365)

    renewal_id = admin_lease_renewal_service.renew_lease(
        admin_env["admin_id"],
        lease_id,
        expected_end_date=old_end,
        new_end_date=new_end,
        notes="Resident agreed to another twelve months.",
    )

    with admin_env["session"]() as db:

        lease = db.get(Lease, lease_id)
        renewal = db.get(LeaseRenewal, renewal_id)

        assert lease is not None
        assert lease.status == "active"
        assert lease.end_date == new_end
        assert lease.monthly_rent == Decimal("1500.00")

        assert renewal is not None
        assert renewal.resident_id == resident_id
        assert renewal.apartment_id == apartment_id
        assert renewal.previous_end_date == old_end
        assert renewal.new_end_date == new_end
        assert renewal.monthly_rent == Decimal("1500.00")

        notification = db.scalar(
            select(Notification).where(
                Notification.user_id == resident_id,
                Notification.title == "Lease Extension Recorded",
            )
        )

        assert notification is not None
        assert notification.is_read is False


# ==========================================================
# TEST 2 — CANNOT SHORTEN OR KEEP SAME END DATE
# ==========================================================

def test_lease_renewal_requires_later_end_date(admin_env):

    _, _, lease_id, old_end = (
        _create_renewal_test_lease(admin_env)
    )

    with pytest.raises(ValueError, match="later"):
        admin_lease_renewal_service.renew_lease(
            admin_env["admin_id"],
            lease_id,
            expected_end_date=old_end,
            new_end_date=old_end,
            notes="Attempting renewal without extending date.",
        )

    with admin_env["session"]() as db:

        lease = db.get(Lease, lease_id)

        assert lease.end_date == old_end

        renewals = db.scalars(
            select(LeaseRenewal).where(
                LeaseRenewal.lease_id == lease_id
            )
        ).all()

        assert len(renewals) == 0


# ==========================================================
# TEST 3 — REJECT STALE RENEWAL REQUEST
# ==========================================================

def test_lease_renewal_rejects_stale_end_date(admin_env):

    _, _, lease_id, old_end = (
        _create_renewal_test_lease(admin_env)
    )

    first_new_end = old_end + timedelta(days=365)

    admin_lease_renewal_service.renew_lease(
        admin_env["admin_id"],
        lease_id,
        expected_end_date=old_end,
        new_end_date=first_new_end,
        notes="Original authorized renewal completed.",
    )

    with pytest.raises(ValueError, match="changed"):
        admin_lease_renewal_service.renew_lease(
            admin_env["admin_id"],
            lease_id,
            expected_end_date=old_end,
            new_end_date=old_end + timedelta(days=730),
            notes="Attempting to save an outdated renewal form.",
        )

    with admin_env["session"]() as db:

        lease = db.get(Lease, lease_id)

        assert lease.end_date == first_new_end

        renewals = db.scalars(
            select(LeaseRenewal).where(
                LeaseRenewal.lease_id == lease_id
            )
        ).all()

        assert len(renewals) == 1


# ==========================================================
# TEST 4 — REJECT TERMINATED LEASE
# ==========================================================

def test_lease_renewal_rejects_terminated_lease(admin_env):

    resident_id, _, lease_id, old_end = (
        _create_renewal_test_lease(admin_env)
    )

    admin_tenancy_service.terminate_lease_and_move_out(
        admin_env["admin_id"],
        resident_id,
        reason="Resident completed early move-out.",
    )

    with pytest.raises(ValueError, match="active leases"):
        admin_lease_renewal_service.renew_lease(
            admin_env["admin_id"],
            lease_id,
            expected_end_date=old_end,
            new_end_date=old_end + timedelta(days=365),
            notes="Attempting to renew terminated lease.",
        )

    with admin_env["session"]() as db:

        lease = db.get(Lease, lease_id)

        assert lease.status == "terminated"
        assert lease.end_date == old_end


# ==========================================================
# TEST 5 — RESIDENT CANNOT RENEW LEASE
# ==========================================================

def test_resident_cannot_renew_lease(admin_env):

    _, _, lease_id, old_end = (
        _create_renewal_test_lease(admin_env)
    )

    with pytest.raises(PermissionError):
        admin_lease_renewal_service.renew_lease(
            admin_env["resident_id"],
            lease_id,
            expected_end_date=old_end,
            new_end_date=old_end + timedelta(days=365),
            notes="Unauthorized resident renewal attempt.",
        )

    with admin_env["session"]() as db:

        lease = db.get(Lease, lease_id)

        assert lease.end_date == old_end


# ==========================================================
# TEST 6 — REJECT OVERLAPPING FUTURE LEASE
# ==========================================================

def test_lease_renewal_rejects_overlapping_future_lease(
    admin_env,
):

    resident_id, apartment_id, lease_id, old_end = (
        _create_renewal_test_lease(admin_env)
    )

    # Simulate an apartment that already has a
    # scheduled future lease in the requested period.

    with admin_env["session"]() as db:

        db.add(
            Lease(
                resident_id=resident_id,
                apartment_id=apartment_id,
                start_date=old_end + timedelta(days=1),
                end_date=old_end + timedelta(days=365),
                monthly_rent=Decimal("1500.00"),
                security_deposit=Decimal("0.00"),
                status="scheduled",
            )
        )

    with pytest.raises(ValueError, match="overlaps"):
        admin_lease_renewal_service.renew_lease(
            admin_env["admin_id"],
            lease_id,
            expected_end_date=old_end,
            new_end_date=old_end + timedelta(days=365),
            notes="Attempting renewal into a reserved period.",
        )

    with admin_env["session"]() as db:

        lease = db.get(Lease, lease_id)

        assert lease.end_date == old_end

        history = db.scalars(
            select(LeaseRenewal).where(
                LeaseRenewal.lease_id == lease_id
            )
        ).all()

        assert len(history) == 0

# ==========================================================
# APARTMENT TRANSFER TEST HELPERS
# ==========================================================

def _transfer_test_setup(admin_env):

    resident_id, old_apartment_id = (
        _create_moveout_resident(admin_env)
    )

    new_apartment_id = (
        admin_management_service.create_apartment(
            admin_env["admin_id"],
            unit_number="QA-TRANSFER",
            floor=3,
            bedrooms=2,
            bathrooms=2.0,
            monthly_rent=1900,
        )
    )

    with admin_env["session"]() as db:

        lease = db.scalar(
            select(Lease).where(
                Lease.resident_id == resident_id,
                Lease.status == "active",
            )
        )

        assert lease is not None

        return (
            resident_id,
            old_apartment_id,
            new_apartment_id,
            lease.id,
            lease.end_date,
        )


# ==========================================================
# TEST 1 — SUCCESSFUL TRANSFER
# ==========================================================

def test_apartment_transfer_preserves_history(admin_env):

    (
        resident_id,
        old_apartment_id,
        new_apartment_id,
        old_lease_id,
        old_end_date,
    ) = _transfer_test_setup(admin_env)

    # Payment remains linked to the original lease.

    with admin_env["session"]() as db:

        db.add(
            Payment(
                resident_id=resident_id,
                lease_id=old_lease_id,
                amount=Decimal("1500.00"),
                payment_month=date.today().replace(day=1),
                payment_method="Bank Transfer",
                status="confirmed",
                confirmation_number="QA-TRANSFER-PAY-001",
            )
        )

    transfer_id = (
        admin_apartment_transfer_service.transfer_resident(
            admin_env["admin_id"],
            old_lease_id,
            expected_apartment_id=old_apartment_id,
            expected_end_date=old_end_date,
            new_apartment_id=new_apartment_id,
            reason="Resident requested a transfer to another unit.",
        )
    )

    with admin_env["session"]() as db:

        resident = db.get(User, resident_id)

        old_apartment = db.get(
            Apartment,
            old_apartment_id,
        )

        new_apartment = db.get(
            Apartment,
            new_apartment_id,
        )

        old_lease = db.get(
            Lease,
            old_lease_id,
        )

        transfer = db.get(
            ApartmentTransfer,
            transfer_id,
        )

        new_lease = db.get(
            Lease,
            transfer.new_lease_id,
        )

        payment = db.scalar(
            select(Payment).where(
                Payment.resident_id == resident_id,
            )
        )

        notification = db.scalar(
            select(Notification).where(
                Notification.user_id == resident_id,
                Notification.title == "Apartment Transfer Completed",
            )
        )

        assert resident.is_active is True
        assert resident.apartment_id == new_apartment_id

        assert old_apartment.is_occupied is False
        assert new_apartment.is_occupied is True

        assert old_lease.status == "transferred"
        assert old_lease.end_date >= old_lease.start_date

        assert new_lease.status == "active"
        assert new_lease.start_date == date.today()
        assert new_lease.end_date == old_end_date
        assert new_lease.apartment_id == new_apartment_id

        # The old monthly rent carries forward.

        assert new_lease.monthly_rent == Decimal("1500.00")
        assert new_lease.security_deposit == Decimal("500.00")

        # The original payment was not moved.

        assert payment is not None
        assert payment.lease_id == old_lease_id

        # Original contractual expiration is auditable.

        assert transfer.previous_contract_end_date == old_end_date
        assert transfer.previous_lease_id == old_lease_id
        assert transfer.new_lease_id == new_lease.id

        assert notification is not None


# ==========================================================
# TEST 2 — REJECT OCCUPIED DESTINATION
# ==========================================================

def test_transfer_rejects_occupied_apartment(admin_env):

    (
        resident_id,
        old_apartment_id,
        destination_id,
        lease_id,
        old_end,
    ) = _transfer_test_setup(admin_env)

    today = date.today()

    # Occupy the desired destination first.

    admin_management_service.create_resident(
        admin_env["admin_id"],
        first_name="Another",
        last_name="Tenant",
        email="other.transfer@example.com",
        password="TemporaryPassword123!",
        apartment_id=destination_id,
        lease_start=today,
        lease_end=today + timedelta(days=365),
    )

    with pytest.raises(
        ValueError,
        match="overlapping|already occupied|existing active lease",
    ):
        admin_apartment_transfer_service.transfer_resident(
            admin_env["admin_id"],
            lease_id,
            expected_apartment_id=old_apartment_id,
            expected_end_date=old_end,
            new_apartment_id=destination_id,
            reason="Attempting to assign an occupied apartment.",
        )

    with admin_env["session"]() as db:

        resident = db.get(User, resident_id)
        lease = db.get(Lease, lease_id)

        assert resident.apartment_id == old_apartment_id
        assert lease.status == "active"
        assert lease.end_date == old_end


# ==========================================================
# TEST 3 — CANNOT TRANSFER TO THE SAME APARTMENT
# ==========================================================

def test_transfer_rejects_same_apartment(admin_env):

    (
        _,
        old_apartment_id,
        _,
        lease_id,
        old_end,
    ) = _transfer_test_setup(admin_env)

    with pytest.raises(
        ValueError,
        match="different apartment",
    ):
        admin_apartment_transfer_service.transfer_resident(
            admin_env["admin_id"],
            lease_id,
            expected_apartment_id=old_apartment_id,
            expected_end_date=old_end,
            new_apartment_id=old_apartment_id,
            reason="Attempting transfer without changing units.",
        )


# ==========================================================
# TEST 4 — REJECT STALE TRANSFER FORM
# ==========================================================

def test_transfer_rejects_stale_lease(admin_env):

    (
        resident_id,
        old_apartment_id,
        new_apartment_id,
        lease_id,
        old_end,
    ) = _transfer_test_setup(admin_env)

    # Another administrator renews the lease first.

    admin_lease_renewal_service.renew_lease(
        admin_env["admin_id"],
        lease_id,
        expected_end_date=old_end,
        new_end_date=old_end + timedelta(days=365),
        notes="Lease was renewed before transfer submission.",
    )

    with pytest.raises(
        ValueError,
        match="changed",
    ):
        admin_apartment_transfer_service.transfer_resident(
            admin_env["admin_id"],
            lease_id,
            expected_apartment_id=old_apartment_id,
            expected_end_date=old_end,
            new_apartment_id=new_apartment_id,
            reason="Attempting to submit an outdated transfer form.",
        )

    with admin_env["session"]() as db:

        resident = db.get(User, resident_id)

        destination = db.get(
            Apartment,
            new_apartment_id,
        )

        assert resident.apartment_id == old_apartment_id
        assert destination.is_occupied is False


# ==========================================================
# TEST 5 — RESIDENT CANNOT TRANSFER ACCOUNTS
# ==========================================================

def test_resident_cannot_transfer_apartment(admin_env):

    (
        _,
        old_apartment_id,
        new_apartment_id,
        lease_id,
        old_end,
    ) = _transfer_test_setup(admin_env)

    with pytest.raises(PermissionError):

        admin_apartment_transfer_service.transfer_resident(
            admin_env["resident_id"],
            lease_id,
            expected_apartment_id=old_apartment_id,
            expected_end_date=old_end,
            new_apartment_id=new_apartment_id,
            reason="Unauthorized resident apartment transfer.",
        )


# ==========================================================
# TEST 6 — PREVENT OVERLAP WITH RESERVED FUTURE LEASE
# ==========================================================

def test_transfer_rejects_future_reservation(admin_env):

    (
        _,
        old_apartment_id,
        new_apartment_id,
        lease_id,
        old_end,
    ) = _transfer_test_setup(admin_env)

    today = date.today()

    # Destination is vacant today but reserved for
    # another future lease.

    with admin_env["session"]() as db:

        db.add(
            Lease(
                resident_id=admin_env["resident_id"],
                apartment_id=new_apartment_id,
                start_date=today + timedelta(days=10),
                end_date=today + timedelta(days=100),
                monthly_rent=Decimal("1900.00"),
                security_deposit=Decimal("0.00"),
                status="scheduled",
            )
        )

    with pytest.raises(
        ValueError,
        match="overlapping",
    ):
        admin_apartment_transfer_service.transfer_resident(
            admin_env["admin_id"],
            lease_id,
            expected_apartment_id=old_apartment_id,
            expected_end_date=old_end,
            new_apartment_id=new_apartment_id,
            reason="Attempting transfer into a reserved unit.",
        )

    with admin_env["session"]() as db:

        old_lease = db.get(
            Lease,
            lease_id,
        )

        assert old_lease.status == "active"
        assert old_lease.end_date == old_end


# ==========================================================
# MOVE-OUT INSPECTION TEST HELPERS
# ==========================================================

def _create_pending_moveout_inspection(admin_env):
    """Create a move-out and return its pending inspection."""

    resident_id, apartment_id = _create_moveout_resident(
        admin_env
    )

    admin_tenancy_service.terminate_lease_and_move_out(
        admin_env["admin_id"],
        resident_id,
        reason="Resident completed an early move-out.",
    )

    with admin_env["session"]() as db:

        inspection = db.scalar(
            select(MoveOutInspection).where(
                MoveOutInspection.apartment_id == apartment_id
            )
        )

        assert inspection is not None

        return (
            resident_id,
            apartment_id,
            inspection.id,
        )


def _save_test_inspection(
    admin_env,
    inspection_id,
    *,
    cleanliness="Good",
    access_secured=True,
    repairs_completed=True,
):
    """Record a complete inspection report."""

    admin_moveout_inspection_service.record_inspection(
        admin_env["admin_id"],
        inspection_id,
        cleanliness=cleanliness,
        walls_floors="Good",
        appliances="Good",
        keys_returned=True,
        access_secured=access_secured,
        repairs_completed=repairs_completed,
        damage_notes="No structural damage observed.",
        inspection_notes=(
            "Apartment inspected and findings recorded."
        ),
        estimated_repair_cost=0,
    )


# ==========================================================
# TEST 1 — MOVE-OUT CREATES A MANDATORY HOLD
# ==========================================================

def test_moveout_creates_inspection_hold(admin_env):

    _, apartment_id, inspection_id = (
        _create_pending_moveout_inspection(admin_env)
    )

    with admin_env["session"]() as db:

        apartment = db.get(
            Apartment,
            apartment_id,
        )

        inspection = db.get(
            MoveOutInspection,
            inspection_id,
        )

        assert apartment.is_occupied is False
        assert inspection.status == "pending"
        assert inspection.source == "move_out"

    # Although physically vacant, the unit
    # cannot be assigned to another resident.

    today = date.today()

    with pytest.raises(
        ValueError,
        match="inspection hold",
    ):

        admin_management_service.create_resident(
            admin_env["admin_id"],
            first_name="New",
            last_name="Applicant",
            email="inspection.blocked@example.com",
            password="TemporaryPassword123!",
            apartment_id=apartment_id,
            lease_start=today,
            lease_end=today + timedelta(days=365),
        )


# ==========================================================
# TEST 2 — CANNOT APPROVE WITHOUT INSPECTION
# ==========================================================

def test_inspection_must_be_completed_before_approval(
    admin_env,
):

    _, _, inspection_id = (
        _create_pending_moveout_inspection(admin_env)
    )

    with pytest.raises(
        ValueError,
        match="Complete the inspection",
    ):

        admin_moveout_inspection_service.approve_inspection(
            admin_env["admin_id"],
            inspection_id,
        )

    with admin_env["session"]() as db:

        inspection = db.get(
            MoveOutInspection,
            inspection_id,
        )

        assert inspection.status == "pending"


# ==========================================================
# TEST 3 — APPROVAL RELEASES APARTMENT
# ==========================================================

def test_approved_inspection_releases_apartment(admin_env):

    _, apartment_id, inspection_id = (
        _create_pending_moveout_inspection(admin_env)
    )

    _save_test_inspection(
        admin_env,
        inspection_id,
    )

    admin_moveout_inspection_service.approve_inspection(
        admin_env["admin_id"],
        inspection_id,
    )

    with admin_env["session"]() as db:

        inspection = db.get(
            MoveOutInspection,
            inspection_id,
        )

        assert inspection.status == "approved"
        assert inspection.approved_by == admin_env["admin_id"]
        assert inspection.approved_at is not None

    blocked = (
        admin_moveout_inspection_service
        .get_blocked_apartment_ids(admin_env["admin_id"])
    )

    assert apartment_id not in blocked

    # Assignment must now succeed.

    today = date.today()

    new_resident_id = admin_management_service.create_resident(
        admin_env["admin_id"],
        first_name="New",
        last_name="Resident",
        email="approved.unit@example.com",
        password="TemporaryPassword123!",
        apartment_id=apartment_id,
        lease_start=today,
        lease_end=today + timedelta(days=365),
    )

    with admin_env["session"]() as db:

        resident = db.get(User, new_resident_id)
        apartment = db.get(Apartment, apartment_id)

        assert resident.apartment_id == apartment_id
        assert apartment.is_occupied is True


# ==========================================================
# TEST 4 — REPAIRS MUST BE COMPLETED
# ==========================================================

def test_inspection_repair_hold_until_completed(admin_env):

    _, apartment_id, inspection_id = (
        _create_pending_moveout_inspection(admin_env)
    )

    _save_test_inspection(
        admin_env,
        inspection_id,
        cleanliness="Needs Repair",
        repairs_completed=False,
    )

    with pytest.raises(
        ValueError,
        match="Complete required repairs",
    ):

        admin_moveout_inspection_service.approve_inspection(
            admin_env["admin_id"],
            inspection_id,
        )

    assert apartment_id in (
        admin_moveout_inspection_service
        .get_blocked_apartment_ids(admin_env["admin_id"])
    )

    # Manager can revise the report after
    # the required work has actually been completed.

    _save_test_inspection(
        admin_env,
        inspection_id,
        cleanliness="Good",
        repairs_completed=True,
    )

    admin_moveout_inspection_service.approve_inspection(
        admin_env["admin_id"],
        inspection_id,
    )

    with admin_env["session"]() as db:

        inspection = db.get(
            MoveOutInspection,
            inspection_id,
        )

        assert inspection.status == "approved"


# ==========================================================
# TEST 5 — TRANSFER HOLDS THE OLD APARTMENT
# ==========================================================

def test_apartment_transfer_creates_inspection_hold(
    admin_env,
):

    (
        _,
        old_apartment_id,
        new_apartment_id,
        lease_id,
        old_end,
    ) = _transfer_test_setup(admin_env)

    admin_apartment_transfer_service.transfer_resident(
        admin_env["admin_id"],
        lease_id,
        expected_apartment_id=old_apartment_id,
        expected_end_date=old_end,
        new_apartment_id=new_apartment_id,
        reason="Transfer approved after resident request.",
    )

    with admin_env["session"]() as db:

        inspection = db.scalar(
            select(MoveOutInspection).where(
                MoveOutInspection.apartment_id == old_apartment_id
            )
        )

        assert inspection is not None
        assert inspection.source == "transfer"
        assert inspection.status == "pending"

        old_apartment = db.get(
            Apartment,
            old_apartment_id,
        )

        new_apartment = db.get(
            Apartment,
            new_apartment_id,
        )

        assert old_apartment.is_occupied is False
        assert new_apartment.is_occupied is True

    destinations = (
        admin_apartment_transfer_service
        .get_transfer_destinations(admin_env["admin_id"])
    )

    destination_ids = {
        item["id"]
        for item in destinations
    }

    assert old_apartment_id not in destination_ids


# ==========================================================
# TEST 6 — ARCHIVE AN ASSIGNED LEGACY TENANT
# ==========================================================

def test_archive_assigned_tenant_creates_inspection(
    admin_env,
):

    resident_id = admin_env["resident_id"]
    apartment_id = admin_env["apartment_id"]

    admin_tenancy_service.archive_resident(
        admin_env["admin_id"],
        resident_id,
        reason="Legacy resident has moved out permanently.",
    )

    with admin_env["session"]() as db:

        inspection = db.scalar(
            select(MoveOutInspection).where(
                MoveOutInspection.apartment_id == apartment_id
            )
        )

        assert inspection is not None
        assert inspection.status == "pending"
        assert inspection.source == "archive"

    assert apartment_id in (
        admin_moveout_inspection_service
        .get_blocked_apartment_ids(admin_env["admin_id"])
    )


# ==========================================================
# TEST 7 — RESIDENT CANNOT CONTROL INSPECTIONS
# ==========================================================

def test_resident_cannot_approve_inspection(admin_env):

    _, _, inspection_id = (
        _create_pending_moveout_inspection(admin_env)
    )

    unauthorized_id = admin_env["resident_id"]

    with pytest.raises(PermissionError):

        admin_moveout_inspection_service.record_inspection(
            unauthorized_id,
            inspection_id,
            cleanliness="Good",
            walls_floors="Good",
            appliances="Good",
            keys_returned=True,
            access_secured=True,
            repairs_completed=True,
            damage_notes="",
            inspection_notes="Unauthorized inspection attempt.",
            estimated_repair_cost=0,
        )

    with pytest.raises(PermissionError):

        admin_moveout_inspection_service.approve_inspection(
            unauthorized_id,
            inspection_id,
        )


# ==========================================================
# SECURITY DEPOSIT TEST HELPERS
# ==========================================================

def _deposit_test_setup(admin_env, approve_inspection=True):
    """Create a terminated demo lease with a $500 deposit."""

    resident_id, _, inspection_id = (
        _create_pending_moveout_inspection(admin_env)
    )

    with admin_env["session"]() as db:
        lease = db.scalar(
            select(Lease).where(
                Lease.resident_id == resident_id,
                Lease.status == "terminated",
            )
        )
        assert lease is not None
        lease_id = lease.id

    if approve_inspection:
        _save_test_inspection(admin_env, inspection_id)

        admin_moveout_inspection_service.approve_inspection(
            admin_env["admin_id"],
            inspection_id,
        )

    return lease_id, inspection_id


# ==========================================================
# TEST 1 — ACTIVE LEASE IS NOT ELIGIBLE
# ==========================================================

def test_deposit_rejects_active_lease(admin_env):

    resident_id, _ = _create_moveout_resident(admin_env)

    with admin_env["session"]() as db:
        lease = db.scalar(
            select(Lease).where(
                Lease.resident_id == resident_id
            )
        )
        lease_id = lease.id

    with pytest.raises(ValueError, match="terminated"):
        admin_deposit_settlement_service.create_deposit_settlement(
            admin_env["admin_id"],
            lease_id,
            notes="Preparing security deposit settlement.",
        )


# ==========================================================
# TEST 2 — ITEMIZED DEDUCTIONS AND INSPECTION APPROVAL
# ==========================================================

def test_deposit_deductions_and_approval(admin_env):

    lease_id, inspection_id = _deposit_test_setup(
        admin_env,
        approve_inspection=False,
    )

    settlement_id = (
        admin_deposit_settlement_service.create_deposit_settlement(
            admin_env["admin_id"],
            lease_id,
            notes="Documenting the final apartment condition.",
        )
    )

    admin_deposit_settlement_service.add_deposit_deduction(
        admin_env["admin_id"],
        settlement_id,
        category="Cleaning",
        description="Additional apartment cleaning completed.",
        amount="125.00",
    )

    with pytest.raises(ValueError, match="exceed"):
        admin_deposit_settlement_service.add_deposit_deduction(
            admin_env["admin_id"],
            settlement_id,
            category="Repairs",
            description="Proposed additional repair deduction.",
            amount="400.00",
        )

    with pytest.raises(ValueError, match="move-out inspection"):
        admin_deposit_settlement_service.approve_deposit_settlement(
            admin_env["admin_id"],
            settlement_id,
        )

    _save_test_inspection(admin_env, inspection_id)

    admin_moveout_inspection_service.approve_inspection(
        admin_env["admin_id"],
        inspection_id,
    )

    admin_deposit_settlement_service.approve_deposit_settlement(
        admin_env["admin_id"],
        settlement_id,
    )

    with admin_env["session"]() as db:
        settlement = db.get(DepositSettlement, settlement_id)

        assert settlement.status == "approved"
        assert settlement.deposit_amount == Decimal("500.00")
        assert settlement.approved_deductions == Decimal("125.00")
        assert settlement.approved_refund == Decimal("375.00")

    # Approved deductions cannot be changed afterward.
    with pytest.raises(ValueError, match="draft"):
        admin_deposit_settlement_service.add_deposit_deduction(
            admin_env["admin_id"],
            settlement_id,
            category="Other",
            description="Attempting to modify approved deductions.",
            amount="1.00",
        )


# ==========================================================
# TEST 3 — EXTERNAL REFUND RECORDING
# ==========================================================

def test_deposit_external_refund_recording(admin_env):

    lease_id, _ = _deposit_test_setup(admin_env)

    settlement_id = (
        admin_deposit_settlement_service.create_deposit_settlement(
            admin_env["admin_id"],
            lease_id,
            notes="Full deposit refund after approved inspection.",
        )
    )

    admin_deposit_settlement_service.approve_deposit_settlement(
        admin_env["admin_id"],
        settlement_id,
    )

    with pytest.raises(ValueError, match="match"):
        admin_deposit_settlement_service.record_external_refund(
            admin_env["admin_id"],
            settlement_id,
            confirmed_amount="499.00",
            refund_method="Bank Transfer",
            refund_reference="QA-REFUND-1001",
            refunded_on=date.today(),
        )

    admin_deposit_settlement_service.record_external_refund(
        admin_env["admin_id"],
        settlement_id,
        confirmed_amount="500.00",
        refund_method="Bank Transfer",
        refund_reference="QA-REFUND-1001",
        refunded_on=date.today(),
    )

    with admin_env["session"]() as db:
        settlement = db.get(DepositSettlement, settlement_id)

        assert settlement.status == "refunded"
        assert settlement.approved_refund == Decimal("500.00")
        assert settlement.refund_reference == "QA-REFUND-1001"

        events = db.scalars(
            select(DepositSettlementEvent).where(
                DepositSettlementEvent.settlement_id == settlement_id
            )
        ).all()

        assert any(
            event.action == "refund_recorded"
            for event in events
        )

    with pytest.raises(ValueError, match="approved"):
        admin_deposit_settlement_service.record_external_refund(
            admin_env["admin_id"],
            settlement_id,
            confirmed_amount="500.00",
            refund_method="Bank Transfer",
            refund_reference="QA-REFUND-1002",
            refunded_on=date.today(),
        )


# ==========================================================
# TEST 4 — ZERO-REFUND SETTLEMENT
# ==========================================================

def test_deposit_close_with_zero_refund(admin_env):

    lease_id, _ = _deposit_test_setup(admin_env)

    settlement_id = (
        admin_deposit_settlement_service.create_deposit_settlement(
            admin_env["admin_id"],
            lease_id,
            notes="Approved itemized deductions use entire deposit.",
        )
    )

    admin_deposit_settlement_service.add_deposit_deduction(
        admin_env["admin_id"],
        settlement_id,
        category="Repairs",
        description="Documented repair work following inspection.",
        amount="500.00",
    )

    admin_deposit_settlement_service.approve_deposit_settlement(
        admin_env["admin_id"],
        settlement_id,
    )

    admin_deposit_settlement_service.close_zero_refund_settlement(
        admin_env["admin_id"],
        settlement_id,
    )

    with admin_env["session"]() as db:
        item = db.get(DepositSettlement, settlement_id)

        assert item.status == "closed_no_refund"
        assert item.approved_refund == Decimal("0.00")
        assert item.closed_at is not None


# ==========================================================
# TEST 5 — RESIDENT CANNOT MODIFY DEPOSIT SETTLEMENTS
# ==========================================================

def test_resident_cannot_create_deposit_settlement(admin_env):

    lease_id, _ = _deposit_test_setup(admin_env)

    with pytest.raises(PermissionError):
        admin_deposit_settlement_service.create_deposit_settlement(
            admin_env["resident_id"],
            lease_id,
            notes="Unauthorized deposit settlement attempt.",
        )


# ==========================================================
# APARTMENT AVAILABILITY TEST HELPER
# ==========================================================

def _availability_row(admin_env, apartment_id):

    rows = (
        admin_apartment_availability_service
        .get_apartment_availability(
            admin_env["admin_id"]
        )
    )

    return next(
        item
        for item in rows
        if item["apartment_id"] == apartment_id
    )


# ==========================================================
# TEST 1 — NEW VACANT APARTMENT IS AVAILABLE
# ==========================================================

def test_availability_dashboard_vacant_new_unit(admin_env):

    apartment_id = (
        admin_management_service.create_apartment(
            admin_env["admin_id"],
            unit_number="QA-AVAIL-EMPTY",
            floor=2,
            bedrooms=1,
            bathrooms=1.0,
            monthly_rent=1200,
        )
    )

    row = _availability_row(
        admin_env,
        apartment_id,
    )

    assert row["status"] == (
        admin_apartment_availability_service.AVAILABLE
    )

    assert row["ready_for_assignment"] is True


# ==========================================================
# TEST 2 — ASSIGNED RESIDENT IS OCCUPIED
# ==========================================================

def test_availability_dashboard_occupied_resident(admin_env):

    resident_id, apartment_id = (
        _create_moveout_resident(admin_env)
    )

    row = _availability_row(
        admin_env,
        apartment_id,
    )

    assert row["status"] == (
        admin_apartment_availability_service.OCCUPIED
    )

    assert row["ready_for_assignment"] is False


# ==========================================================
# TEST 3 — INSPECTION STATUS WORKFLOW
# ==========================================================

def test_availability_dashboard_inspection_workflow(
    admin_env,
):

    resident_id, apartment_id, inspection_id = (
        _create_pending_moveout_inspection(admin_env)
    )

    # --------------------------------------
    # PENDING INSPECTION
    # --------------------------------------

    row = _availability_row(
        admin_env,
        apartment_id,
    )

    assert row["status"] == (
        admin_apartment_availability_service
        .INSPECTION_PENDING
    )

    assert row["ready_for_assignment"] is False

    # --------------------------------------
    # INSPECTION FINDS DAMAGE
    # --------------------------------------

    admin_moveout_inspection_service.record_inspection(
        admin_env["admin_id"],
        inspection_id,
        cleanliness="Needs Repair",
        walls_floors="Good",
        appliances="Good",
        keys_returned=True,
        access_secured=True,
        repairs_completed=False,
        damage_notes="Carpet damage was documented.",
        inspection_notes=(
            "Floor cleaning and repairs are required."
        ),
        estimated_repair_cost="100.00",
    )

    row = _availability_row(
        admin_env,
        apartment_id,
    )

    assert row["status"] == (
        admin_apartment_availability_service
        .REPAIRS_REQUIRED
    )

    assert row["estimated_repairs"] == Decimal("100.00")

    # --------------------------------------
    # INSPECTION UPDATED AFTER REPAIRS
    # --------------------------------------

    _save_test_inspection(
        admin_env,
        inspection_id,
    )

    row = _availability_row(
        admin_env,
        apartment_id,
    )

    assert row["status"] == (
        admin_apartment_availability_service
        .AWAITING_APPROVAL
    )

    # --------------------------------------
    # APPROVAL RELEASES THE APARTMENT
    # --------------------------------------

    admin_moveout_inspection_service.approve_inspection(
        admin_env["admin_id"],
        inspection_id,
    )

    row = _availability_row(
        admin_env,
        apartment_id,
    )

    assert row["status"] == (
        admin_apartment_availability_service.AVAILABLE
    )

    assert row["ready_for_assignment"] is True


# ==========================================================
# TEST 4 — FUTURE LEASE RESERVATION
# ==========================================================

def test_availability_dashboard_future_reservation(
    admin_env,
):

    apartment_id = (
        admin_management_service.create_apartment(
            admin_env["admin_id"],
            unit_number="QA-AVAIL-RESERVED",
            floor=3,
            bedrooms=1,
            bathrooms=1.0,
            monthly_rent=1250,
        )
    )

    today = date.today()

    with admin_env["session"]() as db:

        db.add(
            Lease(
                resident_id=admin_env["resident_id"],
                apartment_id=apartment_id,
                start_date=(
                    today + timedelta(days=15)
                ),
                end_date=(
                    today + timedelta(days=365)
                ),
                monthly_rent=Decimal("1250.00"),
                security_deposit=Decimal("0.00"),
                status="scheduled",
            )
        )

    row = _availability_row(
        admin_env,
        apartment_id,
    )

    assert row["status"] == (
        admin_apartment_availability_service.RESERVED
    )

    assert row["ready_for_assignment"] is False


# ==========================================================
# TEST 5 — RESIDENT CANNOT ACCESS ADMIN DASHBOARD
# ==========================================================

def test_availability_dashboard_resident_denied(
    admin_env,
):

    with pytest.raises(PermissionError):

        (
            admin_apartment_availability_service
            .get_apartment_availability(
                admin_env["resident_id"]
            )
        )

# ==========================================================
# SPRINT 10F — UNIFIED TENANT HISTORY TESTS
# ==========================================================


# ==========================================================
# TEST 1 — ARCHIVED RESIDENT HISTORY REMAINS ACCESSIBLE
# ==========================================================

def test_history_lists_archived_residents(admin_env):

    resident_id, apartment_id = (
        _create_moveout_resident(admin_env)
    )

    admin_tenancy_service.terminate_lease_and_move_out(
        admin_env["admin_id"],
        resident_id,
        reason=(
            "Resident completed move-out "
            "and account archiving."
        ),
    )

    residents = (
        admin_tenant_history_service.get_history_residents(
            admin_env["admin_id"]
        )
    )

    archived = next(
        row
        for row in residents
        if row["id"] == resident_id
    )

    assert archived["active"] is False

    history = (
        admin_tenant_history_service.get_resident_history(
            admin_env["admin_id"],
            resident_id,
        )
    )

    assert history["resident"]["status"] == (
        "Archived / Inactive"
    )

    assert history["summary"]["leases"] == 1
    assert history["summary"]["inspections"] == 1

    assert any(
        event["category"] == "Tenancy"
        for event in history["timeline"]
    )


# ==========================================================
# TEST 2 — TRANSFER PRESERVES LEASE AND PAYMENT HISTORY
# ==========================================================

def test_history_keeps_transfer_old_and_new_leases(
    admin_env,
):

    (
        resident_id,
        old_apartment_id,
        new_apartment_id,
        old_lease_id,
        old_end_date,
    ) = _transfer_test_setup(admin_env)

    # Payment belongs to the original lease.

    with admin_env["session"]() as db:

        db.add(
            Payment(
                resident_id=resident_id,
                lease_id=old_lease_id,
                amount=Decimal("1500.00"),
                payment_month=(
                    date.today().replace(day=1)
                ),
                payment_method="Bank Transfer",
                status="confirmed",
                confirmation_number=(
                    "QA-HISTORY-OLD-LEASE"
                ),
            )
        )

    admin_apartment_transfer_service.transfer_resident(
        admin_env["admin_id"],
        old_lease_id,
        expected_apartment_id=old_apartment_id,
        expected_end_date=old_end_date,
        new_apartment_id=new_apartment_id,
        reason=(
            "Resident requested an approved "
            "apartment transfer."
        ),
    )

    history = (
        admin_tenant_history_service.get_resident_history(
            admin_env["admin_id"],
            resident_id,
        )
    )

    assert history["summary"]["leases"] == 2
    assert history["summary"]["transfers"] == 1

    assert {
        row["Status"]
        for row in history["leases"]
    } == {
        "Active",
        "Transferred",
    }

    assert history["payments"][0][
        "Lease ID"
    ] == old_lease_id

    assert history["summary"][
        "confirmed_payments"
    ] == Decimal("1500.00")

    assert any(
        event["category"] == "Apartment Transfer"
        for event in history["timeline"]
    )


# ==========================================================
# TEST 3 — SECURITY DEPOSIT SETTLEMENT IS INCLUDED
# ==========================================================

def test_history_includes_deposit_settlement_and_deductions(
    admin_env,
):

    lease_id, _ = _deposit_test_setup(
        admin_env
    )

    settlement_id = (
        admin_deposit_settlement_service.create_deposit_settlement(
            admin_env["admin_id"],
            lease_id,
            notes=(
                "Final security deposit accounting "
                "after inspection."
            ),
        )
    )

    admin_deposit_settlement_service.add_deposit_deduction(
        admin_env["admin_id"],
        settlement_id,
        category="Cleaning",
        description=(
            "Documented additional cleaning "
            "after move-out."
        ),
        amount="75.00",
    )

    admin_deposit_settlement_service.approve_deposit_settlement(
        admin_env["admin_id"],
        settlement_id,
    )

    with admin_env["session"]() as db:

        lease = db.get(
            Lease,
            lease_id,
        )

        resident_id = lease.resident_id

    history = (
        admin_tenant_history_service.get_resident_history(
            admin_env["admin_id"],
            resident_id,
        )
    )

    assert history["summary"]["settlements"] == 1

    settlement = history["deposits"][0]

    assert settlement[
        "Approved Refund"
    ] == Decimal("425.00")

    assert history[
        "deductions_by_settlement"
    ][settlement_id][0][
        "Amount"
    ] == Decimal("75.00")

    assert any(
        event["category"] == "Security Deposit"
        for event in history["timeline"]
    )


# ==========================================================
# TEST 4 — TIMELINE IS SORTED NEWEST FIRST
# ==========================================================

def test_history_timeline_is_newest_first(admin_env):

    resident_id, _ = _create_moveout_resident(
        admin_env
    )

    history = (
        admin_tenant_history_service.get_resident_history(
            admin_env["admin_id"],
            resident_id,
        )
    )

    timestamps = [
        admin_tenant_history_service._sort_date(
            row["date"]
        )
        for row in history["timeline"]
    ]

    assert timestamps == sorted(
        timestamps,
        reverse=True,
    )


# ==========================================================
# TEST 5 — RESIDENTS CANNOT ACCESS ADMIN HISTORY
# ==========================================================

def test_history_requires_admin_access(admin_env):

    with pytest.raises(PermissionError):

        admin_tenant_history_service.get_history_residents(
            admin_env["resident_id"]
        )

    with pytest.raises(PermissionError):

        admin_tenant_history_service.get_resident_history(
            admin_env["resident_id"],
            admin_env["resident_id"],
        )

    with pytest.raises(
        ValueError,
        match="Resident not found",
    ):

        admin_tenant_history_service.get_resident_history(
            admin_env["admin_id"],
            admin_env["admin_id"],
        )


# ==========================================================
# SPRINT 11A.2 — LEGACY INTEGRATION TEST ADMIN ROLE
# ==========================================================

@pytest.fixture(autouse=True)
def _grant_integration_test_admin_role(request):
    """
    Give the existing admin_env administrator a
    Super Admin role in its isolated test database.

    This does NOT modify the real application database.
    """

    if "admin_env" not in request.fixturenames:
        return

    admin_env = request.getfixturevalue(
        "admin_env"
    )

    admin_id = admin_env["admin_id"]

    with admin_env["session"]() as db:

        existing = db.scalar(
            select(AdminRoleAssignment.id).where(
                AdminRoleAssignment.user_id == admin_id
            )
        )

        if existing is None:

            db.add(
                AdminRoleAssignment(
                    user_id=admin_id,
                    role="super_admin",
                    assigned_by=admin_id,
                )
            )
