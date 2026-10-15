
"""Sprint 11A — Administrator role-based access control tests."""

from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.admin_permissions import permissions_for
from database.models import (
    AdminEmployee,
    AdminRoleAssignment,
    AdminRoleChangeEvent,
    Apartment,
    Base,
    User,
)
from services import (
    admin_apartment_transfer_service,
    admin_content_service,
    admin_dashboard_service,
    admin_deposit_settlement_service,
    admin_directory_service,
    admin_lease_renewal_service,
    admin_management_service,
    admin_moveout_inspection_service,
    admin_operations_service,
    admin_rbac_service,
    admin_tenancy_service,
)
from components.admin_sidebar import get_visible_admin_pages
from views.admin_apartments import get_apartment_workflows


# ==========================================================
# TEST DATABASE FIXTURE
# ==========================================================

@pytest.fixture()
def roles_env(monkeypatch):
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

    with test_session() as db:
        owner = User(
            first_name="Owner",
            last_name="Manager",
            email="owner.rbac@example.test",
            password_hash="test_only",
            role="admin",
            is_active=True,
        )
        colleague = User(
            first_name="Assistant",
            last_name="Manager",
            email="colleague.rbac@example.test",
            password_hash="test_only",
            role="admin",
            is_active=True,
        )
        resident = User(
            first_name="Sample",
            last_name="Resident",
            email="resident.rbac@example.test",
            password_hash="test_only",
            role="resident",
            is_active=True,
        )

        db.add_all([owner, colleague, resident])
        db.flush()

        db.add_all([
            AdminEmployee(
                user_id=owner.id,
                employee_id="RBAC-100",
                is_active=True,
            ),
            AdminEmployee(
                user_id=colleague.id,
                employee_id="RBAC-200",
                is_active=True,
            ),
        ])

        ids = {
            "owner": owner.id,
            "colleague": colleague.id,
            "resident": resident.id,
        }

    yield ids, test_session
    engine.dispose()


# ==========================================================
# INITIAL ROLE ASSIGNMENT TESTS
# ==========================================================

def test_no_one_receives_a_role_automatically(roles_env):
    ids, _ = roles_env
    data = admin_rbac_service.get_my_admin_access(ids["owner"])
    assert data["role"] is None
    assert data["permissions"] == []


def test_one_time_explicit_super_admin_bootstrap(roles_env):
    ids, _ = roles_env

    created = admin_rbac_service.bootstrap_initial_super_admin(
        "OWNER.RBAC@EXAMPLE.TEST"
    )

    assert created == ids["owner"]
    assert (
        admin_rbac_service.get_my_admin_access(
            ids["owner"]
        )["role"]
        == "super_admin"
    )

    with pytest.raises(ValueError, match="already been performed"):
        admin_rbac_service.bootstrap_initial_super_admin(
            "colleague.rbac@example.test"
        )


def test_residents_cannot_be_promoted_via_bootstrap(roles_env):
    with pytest.raises(PermissionError):
        admin_rbac_service.bootstrap_initial_super_admin(
            "resident.rbac@example.test"
        )


def test_super_admin_role_assignment_is_audited(roles_env):
    ids, test_session = roles_env

    admin_rbac_service.bootstrap_initial_super_admin(
        "owner.rbac@example.test"
    )

    admin_rbac_service.assign_admin_role(
        ids["owner"],
        ids["colleague"],
        "finance_manager",
        reason="Appointed to manage deposit settlements",
    )

    access = admin_rbac_service.get_my_admin_access(
        ids["colleague"]
    )

    assert access["role"] == "finance_manager"
    assert "deposits.approve" in access["permissions"]
    assert "admins.manage" not in access["permissions"]

    with test_session() as db:
        events = db.scalars(
            select(AdminRoleChangeEvent)
        ).all()

        assert len(events) == 2
        assert events[-1].previous_role is None
        assert events[-1].new_role == "finance_manager"


def test_non_super_admin_cannot_assign_roles(roles_env):
    ids, _ = roles_env

    admin_rbac_service.bootstrap_initial_super_admin(
        "owner.rbac@example.test"
    )

    with pytest.raises(PermissionError, match="Super Admin"):
        admin_rbac_service.assign_admin_role(
            ids["colleague"],
            ids["owner"],
            "auditor",
            reason="Unauthorized attempt to change roles",
        )


def test_super_admin_cannot_change_own_role(roles_env):
    ids, _ = roles_env

    admin_rbac_service.bootstrap_initial_super_admin(
        "owner.rbac@example.test"
    )

    with pytest.raises(ValueError, match="own role"):
        admin_rbac_service.assign_admin_role(
            ids["owner"],
            ids["owner"],
            "auditor",
            reason="Attempt to remove the last owner",
        )


def test_inactive_admin_employee_cannot_access_roles(roles_env):
    ids, test_session = roles_env

    with test_session() as db:
        employee = db.scalar(
            select(AdminEmployee).where(
                AdminEmployee.user_id == ids["owner"]
            )
        )
        employee.is_active = False

    with pytest.raises(PermissionError, match="employee"):
        admin_rbac_service.get_my_admin_access(ids["owner"])


def test_role_policy_rejects_unknown_role():
    assert permissions_for(None) == frozenset()
    assert permissions_for("invented_role") == frozenset()
    assert "tenants.create" not in permissions_for("auditor")
    assert "deposits.approve" in permissions_for("super_admin")


# ==========================================================
# MANAGEMENT SERVICE HELPERS
# ==========================================================

def _enable_management_test_db(monkeypatch, roles_env):
    ids, test_session = roles_env
    monkeypatch.setattr(
        admin_management_service,
        "get_db_session",
        test_session,
    )
    return ids, test_session


def _test_apartment(admin_id, unit_number):
    return admin_management_service.create_apartment(
        admin_id,
        unit_number=unit_number,
        floor=2,
        bedrooms=2,
        bathrooms=1.0,
        monthly_rent="1450.00",
    )


# ==========================================================
# RESIDENT AND APARTMENT WRITE PERMISSIONS
# ==========================================================

def test_rbac_unassigned_admin_cannot_create_apartment(
    roles_env, monkeypatch
):
    ids, _ = _enable_management_test_db(
        monkeypatch, roles_env
    )

    with pytest.raises(PermissionError, match="apartments.create"):
        _test_apartment(ids["owner"], "RBAC-UNASSIGNED")


def test_rbac_auditor_cannot_edit_apartment(
    roles_env, monkeypatch
):
    ids, _ = _enable_management_test_db(
        monkeypatch, roles_env
    )

    admin_rbac_service.bootstrap_initial_super_admin(
        "owner.rbac@example.test"
    )

    apartment_id = _test_apartment(
        ids["owner"], "RBAC-AUDIT"
    )

    admin_rbac_service.assign_admin_role(
        ids["owner"],
        ids["colleague"],
        "auditor",
        reason="Read-only auditing responsibilities",
    )

    with pytest.raises(PermissionError, match="apartments.update"):
        admin_management_service.update_apartment(
            ids["colleague"],
            apartment_id,
            unit_number="RBAC-AUDIT-EDIT",
            floor=2,
            bedrooms=2,
            bathrooms=1.0,
            monthly_rent="1500.00",
        )


def test_rbac_property_manager_can_manage_apartments(
    roles_env, monkeypatch
):
    ids, test_session = _enable_management_test_db(
        monkeypatch, roles_env
    )

    admin_rbac_service.bootstrap_initial_super_admin(
        "owner.rbac@example.test"
    )

    admin_rbac_service.assign_admin_role(
        ids["owner"],
        ids["colleague"],
        "property_manager",
        reason="Assigned responsibility for property operations",
    )

    apartment_id = _test_apartment(
        ids["colleague"], "RBAC-PROPERTY"
    )

    admin_management_service.update_apartment(
        ids["colleague"],
        apartment_id,
        unit_number="RBAC-PROPERTY-EDIT",
        floor=3,
        bedrooms=2,
        bathrooms=1.0,
        monthly_rent="1550.00",
    )

    with test_session() as db:
        apartment = db.get(Apartment, apartment_id)
        assert apartment.unit_number == "RBAC-PROPERTY-EDIT"
        assert apartment.monthly_rent == Decimal("1550.00")


def test_rbac_leasing_agent_resident_permissions(
    roles_env, monkeypatch
):
    ids, test_session = _enable_management_test_db(
        monkeypatch, roles_env
    )

    admin_rbac_service.bootstrap_initial_super_admin(
        "owner.rbac@example.test"
    )

    admin_rbac_service.assign_admin_role(
        ids["owner"],
        ids["colleague"],
        "leasing_agent",
        reason="Authorized to register and update new tenants",
    )

    apartment_id = _test_apartment(
        ids["owner"], "RBAC-LEASING"
    )

    resident_id = admin_management_service.create_resident(
        ids["colleague"],
        first_name="Leasing",
        last_name="Test",
        email="leasing.rbac@example.test",
        password="SecureDemoPassword123!",
        apartment_id=apartment_id,
        lease_start=date.today(),
        lease_end=date.today() + timedelta(days=365),
        security_deposit="500.00",
        phone="",
    )

    admin_management_service.update_resident(
        ids["colleague"],
        resident_id,
        first_name="Updated",
        last_name="Test",
        email="leasing.rbac@example.test",
        phone="",
        apartment_id=apartment_id,
        is_active=True,
    )

    with test_session() as db:
        resident = db.get(User, resident_id)
        assert resident.first_name == "Updated"

    with pytest.raises(PermissionError, match="apartments.create"):
        _test_apartment(ids["colleague"], "RBAC-FORBIDDEN")


def test_rbac_finance_manager_cannot_create_resident(
    roles_env, monkeypatch
):
    ids, _ = _enable_management_test_db(
        monkeypatch, roles_env
    )

    admin_rbac_service.bootstrap_initial_super_admin(
        "owner.rbac@example.test"
    )

    admin_rbac_service.assign_admin_role(
        ids["owner"],
        ids["colleague"],
        "finance_manager",
        reason="Limited to financial reporting and settlements",
    )

    apartment_id = _test_apartment(
        ids["owner"], "RBAC-FINANCE"
    )

    with pytest.raises(PermissionError, match="tenants.create"):
        admin_management_service.create_resident(
            ids["colleague"],
            first_name="Forbidden",
            last_name="Creation",
            email="forbidden.rbac@example.test",
            password="SecureDemoPassword123!",
            apartment_id=apartment_id,
            lease_start=date.today(),
            lease_end=date.today() + timedelta(days=365),
            security_deposit="0.00",
            phone="",
        )


# ==========================================================
# REMAINING SERVICE PERMISSION FIXTURE
# ==========================================================

@pytest.fixture()
def remaining_rbac_env(roles_env, monkeypatch):
    ids, test_session = roles_env

    modules = (
        admin_apartment_transfer_service,
        admin_content_service,
        admin_deposit_settlement_service,
        admin_lease_renewal_service,
        admin_moveout_inspection_service,
        admin_operations_service,
        admin_tenancy_service,
    )

    for module in modules:
        monkeypatch.setattr(
            module,
            "get_db_session",
            test_session,
        )

    admin_rbac_service.bootstrap_initial_super_admin(
        "owner.rbac@example.test"
    )

    return ids


def _as_role(ids, role):
    admin_rbac_service.assign_admin_role(
        ids["owner"],
        ids["colleague"],
        role,
        reason=f"Test role assignment for {role} permissions",
    )
    return ids["colleague"]


# ==========================================================
# REMAINING SERVICE PERMISSION TESTS
# ==========================================================

def test_remaining_rbac_auditor_can_read_but_cannot_write(
    remaining_rbac_env,
):
    admin_id = _as_role(remaining_rbac_env, "auditor")

    assert (
        admin_operations_service.get_admin_payments(
            admin_id
        )["total_records"] == 0
    )
    assert admin_content_service.get_admin_announcements(
        admin_id
    ) == []
    assert admin_lease_renewal_service.get_lease_renewal_history(
        admin_id
    ) == []
    assert admin_moveout_inspection_service.get_open_inspections(
        admin_id
    ) == []
    assert admin_deposit_settlement_service.get_deposit_settlements(
        admin_id
    ) == []

    with pytest.raises(PermissionError, match="leases.terminate"):
        admin_tenancy_service.terminate_lease_and_move_out(
            admin_id,
            999,
            reason="Unauthorized move-out attempt",
        )

    with pytest.raises(PermissionError, match="deposits.approve"):
        admin_deposit_settlement_service.approve_deposit_settlement(
            admin_id, 999
        )

    with pytest.raises(PermissionError, match="announcements.manage"):
        admin_content_service.create_admin_announcement(
            admin_id,
            title="An announcement",
            message="A valid message",
            category="General",
            priority="Normal",
            expires_on="",
            published=False,
        )


def test_remaining_rbac_leasing_agent_can_view_blocked_units(
    remaining_rbac_env,
):
    admin_id = _as_role(remaining_rbac_env, "leasing_agent")

    assert admin_lease_renewal_service.get_renewable_leases(
        admin_id
    ) == []
    assert admin_moveout_inspection_service.get_blocked_apartment_ids(
        admin_id
    ) == set()
    assert admin_apartment_transfer_service.get_transfer_destinations(
        admin_id
    ) == []

    with pytest.raises(PermissionError, match="inspections.read"):
        admin_moveout_inspection_service.get_open_inspections(
            admin_id
        )

    with pytest.raises(PermissionError, match="payments.read"):
        admin_operations_service.get_admin_payments(admin_id)

    with pytest.raises(PermissionError, match="transfers.execute"):
        admin_apartment_transfer_service.transfer_resident(
            admin_id,
            999,
            expected_apartment_id=1,
            expected_end_date=date.today(),
            new_apartment_id=2,
            reason="Leasing agent may not transfer an apartment",
        )


def test_remaining_rbac_maintenance_manager_cannot_approve_units(
    remaining_rbac_env,
):
    admin_id = _as_role(remaining_rbac_env, "maintenance_manager")

    assert (
        admin_operations_service.get_admin_maintenance(
            admin_id
        )["total"] == 0
    )

    assert admin_moveout_inspection_service.get_open_inspections(
        admin_id
    ) == []

    with pytest.raises(PermissionError, match="inspections.approve"):
        admin_moveout_inspection_service.approve_inspection(
            admin_id, 999
        )

    with pytest.raises(PermissionError, match="deposits.read"):
        admin_deposit_settlement_service.get_deposit_settlements(
            admin_id
        )


def test_remaining_rbac_finance_manager_cannot_manage_tenancy(
    remaining_rbac_env,
):
    admin_id = _as_role(remaining_rbac_env, "finance_manager")

    assert (
        admin_operations_service.get_admin_payments(
            admin_id
        )["total_records"] == 0
    )
    assert admin_deposit_settlement_service.get_eligible_deposit_leases(
        admin_id
    ) == []

    with pytest.raises(PermissionError, match="tenants.archive"):
        admin_tenancy_service.archive_resident(
            admin_id,
            999,
            reason="Finance cannot archive a resident",
        )

    with pytest.raises(PermissionError, match="maintenance.update"):
        admin_operations_service.update_maintenance_request(
            admin_id,
            999,
            expected_status="Submitted",
            new_status="Scheduled",
            technician_name="Test",
            note="Testing denial",
        )


def test_remaining_rbac_property_manager_cannot_change_deposits(
    remaining_rbac_env,
):
    admin_id = _as_role(remaining_rbac_env, "property_manager")

    assert admin_apartment_transfer_service.get_transfer_candidates(
        admin_id
    ) == []
    assert admin_deposit_settlement_service.get_deposit_settlements(
        admin_id
    ) == []

    with pytest.raises(PermissionError, match="deposits.edit"):
        admin_deposit_settlement_service.create_deposit_settlement(
            admin_id,
            999,
            notes="This is a prohibited financial adjustment",
        )

    with pytest.raises(PermissionError, match="refunds.record"):
        admin_deposit_settlement_service.record_external_refund(
            admin_id,
            999,
            confirmed_amount="1.00",
            refund_method="Check",
            refund_reference="TEST-UNAUTHORIZED",
            refunded_on=date.today(),
        )


# ==========================================================
# CORRECTED ADMINISTRATOR NAVIGATION TESTS
# ==========================================================

@pytest.mark.parametrize(
    "role, expected_pages",
    [
        (
            "super_admin",
            {
                "overview",
                "tenants",
                "apartments",
                "payments",
                "maintenance",
                "announcements",
                "community_news",
                "admin_users",
            },
        ),
        (
            "property_manager",
            {
                "overview",
                "tenants",
                "apartments",
                "payments",
                "maintenance",
                "announcements",
                "community_news",
            },
        ),
        (
            "finance_manager",
            {
                "tenants",
                "payments",
            },
        ),
        (
            "maintenance_manager",
            {
                "tenants",
                "apartments",
                "maintenance",
            },
        ),
        (
            "leasing_agent",
            {
                "tenants",
                "apartments",
            },
        ),
        (
            "auditor",
            {
                "overview",
                "tenants",
                "apartments",
                "payments",
            },
        ),
    ],
)
def test_admin_navigation_matches_role_permissions(
    role,
    expected_pages,
):
    access = {
        "role": role,
        "permissions": list(permissions_for(role)),
    }

    assert get_visible_admin_pages(access) == expected_pages


def test_unassigned_admin_has_no_navigation():
    assert get_visible_admin_pages(
        {"role": None, "permissions": []}
    ) == set()

# ==========================================================
# DIRECTORY AND DASHBOARD RBAC TESTS
# ==========================================================

@pytest.fixture()
def protected_read_env(roles_env, monkeypatch):
    ids, test_session = roles_env

    monkeypatch.setattr(
        admin_directory_service,
        "get_db_session",
        test_session,
    )

    monkeypatch.setattr(
        admin_dashboard_service,
        "get_db_session",
        test_session,
    )

    return ids, test_session


def test_unassigned_admin_cannot_read_directories(
    protected_read_env,
):
    ids, _ = protected_read_env

    with pytest.raises(PermissionError):
        admin_directory_service.get_admin_directory(
            ids["owner"]
        )

    with pytest.raises(PermissionError):
        admin_dashboard_service.get_admin_dashboard_data(
            ids["owner"]
        )


def test_resident_cannot_read_admin_directory(
    protected_read_env,
):
    ids, _ = protected_read_env

    with pytest.raises(PermissionError):
        admin_directory_service.get_admin_directory(
            ids["resident"]
        )


def test_auditor_can_read_overview_and_directories(
    protected_read_env,
):
    ids, _ = protected_read_env

    admin_rbac_service.bootstrap_initial_super_admin(
        "owner.rbac@example.test"
    )

    admin_rbac_service.assign_admin_role(
        ids["owner"],
        ids["colleague"],
        "auditor",
        reason="Authorized read-only auditing responsibilities",
    )

    result = admin_directory_service.get_admin_directory(
        ids["colleague"]
    )

    assert len(result["residents"]) == 1
    assert isinstance(result["apartments"], list)

    overview = admin_dashboard_service.get_admin_dashboard_data(
        ids["colleague"]
    )

    assert overview["total_apartments"] == 0
    assert overview["active_residents"] == 1


def test_finance_manager_cannot_read_apartment_directory(
    protected_read_env,
):
    ids, _ = protected_read_env

    admin_rbac_service.bootstrap_initial_super_admin(
        "owner.rbac@example.test"
    )

    admin_rbac_service.assign_admin_role(
        ids["owner"],
        ids["colleague"],
        "finance_manager",
        reason="Responsible for financial administration",
    )

    residents_only = admin_directory_service.get_admin_directory(
        ids["colleague"],
        include_apartments=False,
    )

    assert len(residents_only["residents"]) == 1
    assert residents_only["apartments"] == []

    with pytest.raises(PermissionError):
        admin_directory_service.get_admin_directory(
            ids["colleague"]
        )

    with pytest.raises(PermissionError):
        admin_dashboard_service.get_admin_dashboard_data(
            ids["colleague"]
        )


def test_maintenance_manager_gets_redacted_apartments(
    protected_read_env,
):
    ids, test_session = protected_read_env

    admin_rbac_service.bootstrap_initial_super_admin(
        "owner.rbac@example.test"
    )

    admin_rbac_service.assign_admin_role(
        ids["owner"],
        ids["colleague"],
        "maintenance_manager",
        reason="Responsible for maintenance operations",
    )

    with test_session() as db:
        apartment = Apartment(
            unit_number="RBAC-101",
            floor=1,
            bedrooms=1,
            bathrooms=Decimal("1.0"),
            monthly_rent=Decimal("1200.00"),
            is_occupied=True,
        )

        db.add(apartment)
        db.flush()

        resident = db.get(
            User,
            ids["resident"],
        )
        resident.apartment_id = apartment.id

    data = admin_directory_service.get_admin_directory(
        ids["colleague"],
        include_residents=False,
    )

    assert data["residents"] == []
    assert len(data["apartments"]) == 1
    assert data["apartments"][0]["resident_count"] == 1
    assert data["apartments"][0]["resident_names"] == "Restricted"

    with pytest.raises(PermissionError):
        admin_directory_service.get_admin_directory(
            ids["colleague"]
        )


# ==========================================================
# APARTMENT WORKFLOW PERMISSION TESTS
# ==========================================================

@pytest.mark.parametrize(
    "role, expected",
    [
        (
            "super_admin",
            {"availability", "directory", "create", "edit"},
        ),
        (
            "property_manager",
            {"directory", "create", "edit"},
        ),
        (
            "leasing_agent",
            {"directory"},
        ),
        (
            "maintenance_manager",
            {"directory"},
        ),
        (
            "auditor",
            {"directory"},
        ),
        (
            "finance_manager",
            set(),
        ),
        (
            None,
            set(),
        ),
    ],
)
def test_role_aware_apartment_workflows(role, expected):
    permissions = permissions_for(role)

    actual = {
        workflow_id
        for workflow_id, _ in get_apartment_workflows(
            permissions
        )
    }

    assert actual == expected


# ==========================================================
# SPRINT 11A.3 — ROLE-AWARE TENANT WORKFLOW TESTS
# ==========================================================

from core.admin_tenant_workflows import (
    get_tenant_workflows,
)


@pytest.mark.parametrize(
    "role, expected_workflows",
    [
        (
            "super_admin",
            {
                "directory",
                "create",
                "edit",
                "lease",
                "archive",
                "renewal",
                "transfer",
                "inspection",
                "deposit",
                "history",
            },
        ),
        (
            "property_manager",
            {
                "directory",
                "create",
                "edit",
                "lease",
                "archive",
                "renewal",
                "transfer",
                "inspection",
                "deposit",
            },
        ),
        (
            "leasing_agent",
            {
                "directory",
                "create",
                "edit",
                "renewal",
            },
        ),
        (
            "maintenance_manager",
            {
                "inspection",
            },
        ),
        (
            "finance_manager",
            {
                "inspection",
                "deposit",
            },
        ),
        (
            "auditor",
            {
                "directory",
                "inspection",
                "deposit",
            },
        ),
        (
            None,
            set(),
        ),
    ],
)
def test_role_aware_tenant_workflows(
    role,
    expected_workflows,
):
    permissions = permissions_for(role)

    actual = {
        workflow_id
        for workflow_id, _ in get_tenant_workflows(
            permissions
        )
    }

    assert actual == expected_workflows


# ==========================================================
# SPRINT 11A.3 — TENANT HISTORY REPORT SECURITY
# ==========================================================

from services import admin_tenant_history_service


@pytest.fixture()
def tenant_history_rbac_env(roles_env, monkeypatch):
    ids, test_session = roles_env

    monkeypatch.setattr(
        admin_tenant_history_service,
        "get_db_session",
        test_session,
    )

    return ids


def test_unassigned_admin_cannot_read_full_tenant_history(
    tenant_history_rbac_env,
):
    ids = tenant_history_rbac_env

    with pytest.raises(
        PermissionError,
        match="admins.manage",
    ):
        admin_tenant_history_service.get_history_residents(
            ids["owner"]
        )

    with pytest.raises(
        PermissionError,
        match="admins.manage",
    ):
        admin_tenant_history_service.get_resident_history(
            ids["owner"],
            ids["resident"],
        )


@pytest.mark.parametrize(
    "role",
    [
        "property_manager",
        "leasing_agent",
        "maintenance_manager",
        "finance_manager",
        "auditor",
    ],
)
def test_restricted_admin_cannot_read_full_tenant_history(
    tenant_history_rbac_env,
    role,
):
    ids = tenant_history_rbac_env

    admin_rbac_service.bootstrap_initial_super_admin(
        "owner.rbac@example.test"
    )

    admin_rbac_service.assign_admin_role(
        ids["owner"],
        ids["colleague"],
        role,
        reason=f"Testing restricted history access for {role}",
    )

    with pytest.raises(PermissionError):
        admin_tenant_history_service.get_history_residents(
            ids["colleague"]
        )

    with pytest.raises(PermissionError):
        admin_tenant_history_service.get_resident_history(
            ids["colleague"],
            ids["resident"],
        )


def test_super_admin_can_read_full_tenant_history(
    tenant_history_rbac_env,
):
    ids = tenant_history_rbac_env

    admin_rbac_service.bootstrap_initial_super_admin(
        "owner.rbac@example.test"
    )

    residents = admin_tenant_history_service.get_history_residents(
        ids["owner"]
    )

    assert len(residents) == 1
    assert residents[0]["id"] == ids["resident"]

    history = admin_tenant_history_service.get_resident_history(
        ids["owner"],
        ids["resident"],
    )

    assert history["resident"]["id"] == ids["resident"]
    assert "payments" in history
    assert "deposits" in history
    assert "timeline" in history



# ==========================================================
# SPRINT 11B.1 — ADMINISTRATOR ACCOUNT CREATION TESTS
# ==========================================================

def _new_admin_data(**overrides):
    fields = {
        "first_name": "Taylor",
        "last_name": "Operations",
        "email": "taylor.admin@example.test",
        "employee_id": "BM-EMP-102",
        "password": "SecureDemoPassword123!",
        "role": "property_manager",
        "reason": (
            "Approved employee for "
            "property management tasks"
        ),
    }

    fields.update(overrides)
    return fields


def test_super_admin_creates_audited_employee_atomically(
    roles_env,
):
    ids, test_session = roles_env

    admin_rbac_service.bootstrap_initial_super_admin(
        "owner.rbac@example.test"
    )

    new_id = admin_rbac_service.create_admin_employee(
        ids["owner"],
        **_new_admin_data(
            email="TAYLOR.ADMIN@EXAMPLE.TEST",
            employee_id="bm-emp-102",
        ),
    )

    with test_session() as db:

        new_user = db.get(User, new_id)

        employee = db.scalar(
            select(AdminEmployee).where(
                AdminEmployee.user_id == new_id
            )
        )

        assignment = db.scalar(
            select(AdminRoleAssignment).where(
                AdminRoleAssignment.user_id == new_id
            )
        )

        event = db.scalar(
            select(AdminRoleChangeEvent).where(
                AdminRoleChangeEvent.target_user_id == new_id
            )
        )

        assert new_user.role == "admin"
        assert new_user.email == "taylor.admin@example.test"

        assert (
            new_user.password_hash
            != "SecureDemoPassword123!"
        )

        assert new_user.is_active is True
        assert new_user.apartment_id is None

        assert employee.employee_id == "BM-EMP-102"
        assert employee.is_active is True

        assert assignment.role == "property_manager"
        assert assignment.assigned_by == ids["owner"]

        assert event.action == "admin_created"
        assert event.actor_user_id == ids["owner"]
        assert event.previous_role is None
        assert event.new_role == "property_manager"


def test_unassigned_admin_cannot_create_administrator(
    roles_env,
):
    ids, _ = roles_env

    with pytest.raises(
        PermissionError,
        match="Super Admin",
    ):
        admin_rbac_service.create_admin_employee(
            ids["owner"],
            **_new_admin_data(),
        )


def test_other_admin_role_cannot_create_administrator(
    roles_env,
):
    ids, _ = roles_env

    admin_rbac_service.bootstrap_initial_super_admin(
        "owner.rbac@example.test"
    )

    admin_rbac_service.assign_admin_role(
        ids["owner"],
        ids["colleague"],
        "property_manager",
        reason=(
            "Approved property management responsibilities"
        ),
    )

    with pytest.raises(
        PermissionError,
        match="Super Admin",
    ):
        admin_rbac_service.create_admin_employee(
            ids["colleague"],
            **_new_admin_data(),
        )


def test_new_admin_cannot_reuse_a_resident_email(
    roles_env,
):
    ids, _ = roles_env

    admin_rbac_service.bootstrap_initial_super_admin(
        "owner.rbac@example.test"
    )

    with pytest.raises(
        ValueError,
        match="email address",
    ):
        admin_rbac_service.create_admin_employee(
            ids["owner"],
            **_new_admin_data(
                email="RESIDENT.RBAC@EXAMPLE.TEST"
            ),
        )


def test_new_admin_employee_id_must_be_unique(
    roles_env,
):
    ids, _ = roles_env

    admin_rbac_service.bootstrap_initial_super_admin(
        "owner.rbac@example.test"
    )

    with pytest.raises(
        ValueError,
        match="employee ID",
    ):
        admin_rbac_service.create_admin_employee(
            ids["owner"],
            **_new_admin_data(
                employee_id="rbac-200"
            ),
        )


@pytest.mark.parametrize(
    "invalid_field, invalid_value",
    [
        ("role", "invented_role"),
        ("password", "short"),
        ("reason", "short"),
    ],
)
def test_new_admin_invalid_fields_rejected(
    roles_env,
    invalid_field,
    invalid_value,
):
    ids, _ = roles_env

    admin_rbac_service.bootstrap_initial_super_admin(
        "owner.rbac@example.test"
    )

    with pytest.raises(ValueError):
        admin_rbac_service.create_admin_employee(
            ids["owner"],
            **_new_admin_data(
                **{
                    invalid_field: invalid_value
                }
            ),
        )


def test_administrator_creation_rolls_back_if_audit_fails(
    roles_env,
    monkeypatch,
):
    ids, test_session = roles_env

    admin_rbac_service.bootstrap_initial_super_admin(
        "owner.rbac@example.test"
    )

    def fail_audit(*args, **kwargs):
        raise RuntimeError(
            "Simulated audit failure"
        )

    monkeypatch.setattr(
        admin_rbac_service,
        "_audit",
        fail_audit,
    )

    with pytest.raises(
        RuntimeError,
        match="Simulated audit failure",
    ):
        admin_rbac_service.create_admin_employee(
            ids["owner"],
            **_new_admin_data(),
        )

    with test_session() as db:

        assert db.scalar(
            select(User.id).where(
                User.email == "taylor.admin@example.test"
            )
        ) is None

        assert db.scalar(
            select(AdminEmployee.id).where(
                AdminEmployee.employee_id == "BM-EMP-102"
            )
        ) is None

# ==========================================================
# SPRINT 11B.2 — ADMIN ACCOUNT STATUS SECURITY TESTS
# ==========================================================

def test_super_admin_deactivates_and_reactivates_employee(
    roles_env,
):
    ids, test_session = roles_env

    admin_rbac_service.bootstrap_initial_super_admin(
        "owner.rbac@example.test"
    )

    admin_rbac_service.assign_admin_role(
        ids["owner"],
        ids["colleague"],
        "finance_manager",
        reason="Approved finance administration responsibilities",
    )

    # Deactivate administrator.

    admin_rbac_service.set_admin_employee_active(
        ids["owner"],
        ids["colleague"],
        active=False,
        reason="Employee administrator access is suspended",
    )

    with test_session() as db:
        user = db.get(User, ids["colleague"])

        employee = db.scalar(
            select(AdminEmployee).where(
                AdminEmployee.user_id == ids["colleague"]
            )
        )

        assignment = db.scalar(
            select(AdminRoleAssignment).where(
                AdminRoleAssignment.user_id == ids["colleague"]
            )
        )

        assert user.is_active is False
        assert employee.is_active is False
        assert assignment.role == "finance_manager"

    with pytest.raises(PermissionError):
        admin_rbac_service.get_my_admin_access(
            ids["colleague"]
        )

    # Reactivate without changing role.

    admin_rbac_service.set_admin_employee_active(
        ids["owner"],
        ids["colleague"],
        active=True,
        reason="Employee administrator access is reinstated",
    )

    access = admin_rbac_service.get_my_admin_access(
        ids["colleague"]
    )

    assert access["role"] == "finance_manager"

    with test_session() as db:
        user = db.get(User, ids["colleague"])

        employee = db.scalar(
            select(AdminEmployee).where(
                AdminEmployee.user_id == ids["colleague"]
            )
        )

        events = db.scalars(
            select(AdminRoleChangeEvent)
            .where(
                AdminRoleChangeEvent.target_user_id
                == ids["colleague"]
            )
            .order_by(AdminRoleChangeEvent.id)
        ).all()

        assert user.is_active is True
        assert employee.is_active is True

        assert events[-2].action == "admin_deactivated"
        assert events[-1].action == "admin_activated"


def test_super_admin_cannot_deactivate_own_account(
    roles_env,
):
    ids, _ = roles_env

    admin_rbac_service.bootstrap_initial_super_admin(
        "owner.rbac@example.test"
    )

    with pytest.raises(ValueError, match="own account status"):
        admin_rbac_service.set_admin_employee_active(
            ids["owner"],
            ids["owner"],
            active=False,
            reason="Attempt to disable my own administrator account",
        )


def test_unassigned_admin_cannot_change_employee_status(
    roles_env,
):
    ids, _ = roles_env

    with pytest.raises(
        PermissionError,
        match="Super Admin",
    ):
        admin_rbac_service.set_admin_employee_active(
            ids["owner"],
            ids["colleague"],
            active=False,
            reason="Unauthorized administrator account change",
        )


def test_non_super_admin_cannot_change_employee_status(
    roles_env,
):
    ids, _ = roles_env

    admin_rbac_service.bootstrap_initial_super_admin(
        "owner.rbac@example.test"
    )

    admin_rbac_service.assign_admin_role(
        ids["owner"],
        ids["colleague"],
        "property_manager",
        reason="Authorized property management responsibilities",
    )

    with pytest.raises(
        PermissionError,
        match="Super Admin",
    ):
        admin_rbac_service.set_admin_employee_active(
            ids["colleague"],
            ids["owner"],
            active=False,
            reason="Unauthorized administrator deactivation attempt",
        )


def test_account_status_change_rejects_noop(
    roles_env,
):
    ids, _ = roles_env

    admin_rbac_service.bootstrap_initial_super_admin(
        "owner.rbac@example.test"
    )

    with pytest.raises(ValueError, match="already active"):
        admin_rbac_service.set_admin_employee_active(
            ids["owner"],
            ids["colleague"],
            active=True,
            reason="Attempting to activate an already active account",
        )


def test_deactivation_preserves_an_active_super_admin(
    roles_env,
):
    ids, _ = roles_env

    admin_rbac_service.bootstrap_initial_super_admin(
        "owner.rbac@example.test"
    )

    admin_rbac_service.assign_admin_role(
        ids["owner"],
        ids["colleague"],
        "super_admin",
        reason="Authorized second Super Admin for system management",
    )

    # One Super Admin can deactivate the other,
    # but cannot deactivate their own account.

    admin_rbac_service.set_admin_employee_active(
        ids["owner"],
        ids["colleague"],
        active=False,
        reason="Second Super Admin account access suspended",
    )

    access = admin_rbac_service.get_my_admin_access(
        ids["owner"]
    )

    assert access["role"] == "super_admin"

    with pytest.raises(ValueError, match="own account status"):
        admin_rbac_service.set_admin_employee_active(
            ids["owner"],
            ids["owner"],
            active=False,
            reason="Attempt to deactivate the remaining owner",
        )


def test_status_update_rolls_back_when_audit_fails(
    roles_env,
    monkeypatch,
):
    ids, test_session = roles_env

    admin_rbac_service.bootstrap_initial_super_admin(
        "owner.rbac@example.test"
    )

    def fail_audit(*args, **kwargs):
        raise RuntimeError("Simulated status audit failure")

    monkeypatch.setattr(
        admin_rbac_service,
        "_audit",
        fail_audit,
    )

    with pytest.raises(
        RuntimeError,
        match="Simulated status audit failure",
    ):
        admin_rbac_service.set_admin_employee_active(
            ids["owner"],
            ids["colleague"],
            active=False,
            reason="Testing atomic administrator status rollback",
        )

    with test_session() as db:
        user = db.get(User, ids["colleague"])

        employee = db.scalar(
            select(AdminEmployee).where(
                AdminEmployee.user_id == ids["colleague"]
            )
        )

        assert user.is_active is True
        assert employee.is_active is True


@pytest.mark.parametrize(
    "active, reason",
    [
        (
            "False",
            "A valid reason for testing invalid status types",
        ),
        (
            True,
            "short",
        ),
    ],
)
def test_account_status_rejects_invalid_arguments(
    roles_env,
    active,
    reason,
):
    ids, _ = roles_env

    admin_rbac_service.bootstrap_initial_super_admin(
        "owner.rbac@example.test"
    )

    with pytest.raises(ValueError):
        admin_rbac_service.set_admin_employee_active(
            ids["owner"],
            ids["colleague"],
            active=active,
            reason=reason,
        )


# ==========================================================
# SPRINT 11B.4A — ADMINISTRATOR PASSWORD SECURITY
# ==========================================================

from core.security import verify_password
from database.models import AdminCredentialState, LoginEvent


def _create_password_test_admin(ids):
    """Create a real administrator with an initial password."""

    return admin_rbac_service.create_admin_employee(
        ids["owner"],
        first_name="Password",
        last_name="Test",
        email="password.admin@example.test",
        employee_id="BM-PASS-101",
        password="InitialPassword123!",
        role="leasing_agent",
        reason="Provisioned for administrator password security testing",
    )


def test_new_administrator_must_change_initial_password(
    roles_env,
):
    ids, test_session = roles_env

    admin_rbac_service.bootstrap_initial_super_admin(
        "owner.rbac@example.test"
    )

    admin_id = _create_password_test_admin(ids)

    access = admin_rbac_service.get_my_admin_access(
        admin_id
    )

    assert access["role"] == "leasing_agent"
    assert access["must_change_password"] is True
    assert access["credential_version"] == 0

    with test_session() as db:
        state = db.get(AdminCredentialState, admin_id)

        assert state is not None
        assert state.must_change_password is True


def test_administrator_can_change_initial_password(
    roles_env,
):
    ids, test_session = roles_env

    admin_rbac_service.bootstrap_initial_super_admin(
        "owner.rbac@example.test"
    )

    admin_id = _create_password_test_admin(ids)

    admin_rbac_service.change_own_admin_password(
        admin_id,
        current_password="InitialPassword123!",
        new_password="UpdatedPassword456!",
        confirm_password="UpdatedPassword456!",
    )

    access = admin_rbac_service.get_my_admin_access(
        admin_id
    )

    assert access["must_change_password"] is False
    assert access["credential_version"] == 1

    with test_session() as db:
        user = db.get(User, admin_id)

        assert verify_password(
            "UpdatedPassword456!",
            user.password_hash,
        )

        assert not verify_password(
            "InitialPassword123!",
            user.password_hash,
        )

        events = db.scalars(
            select(LoginEvent).where(
                LoginEvent.user_id == admin_id,
                LoginEvent.event_type == "password_changed",
            )
        ).all()

        assert len(events) == 1


def test_wrong_current_password_cannot_change_password(
    roles_env,
):
    ids, _ = roles_env

    admin_rbac_service.bootstrap_initial_super_admin(
        "owner.rbac@example.test"
    )

    admin_id = _create_password_test_admin(ids)

    with pytest.raises(ValueError, match="Current password"):
        admin_rbac_service.change_own_admin_password(
            admin_id,
            current_password="WrongPassword123!",
            new_password="UpdatedPassword456!",
            confirm_password="UpdatedPassword456!",
        )

    assert (
        admin_rbac_service.get_my_admin_access(
            admin_id
        )["must_change_password"]
        is True
    )


def test_administrator_cannot_reuse_current_password(
    roles_env,
):
    ids, _ = roles_env

    admin_rbac_service.bootstrap_initial_super_admin(
        "owner.rbac@example.test"
    )

    admin_id = _create_password_test_admin(ids)

    with pytest.raises(ValueError, match="must differ"):
        admin_rbac_service.change_own_admin_password(
            admin_id,
            current_password="InitialPassword123!",
            new_password="InitialPassword123!",
            confirm_password="InitialPassword123!",
        )


@pytest.mark.parametrize(
    "new_password, confirmation",
    [
        ("short", "short"),
        ("lowercasepassword123!", "lowercasepassword123!"),
        ("UPPERCASEPASSWORD123!", "UPPERCASEPASSWORD123!"),
        ("PasswordWithoutNumber!", "PasswordWithoutNumber!"),
        ("PasswordWithoutSymbol123", "PasswordWithoutSymbol123"),
        ("UpdatedPassword456!", "DoesNotMatch123!"),
    ],
)
def test_invalid_new_administrator_password_is_rejected(
    roles_env,
    new_password,
    confirmation,
):
    ids, _ = roles_env

    admin_rbac_service.bootstrap_initial_super_admin(
        "owner.rbac@example.test"
    )

    admin_id = _create_password_test_admin(ids)

    with pytest.raises(ValueError):
        admin_rbac_service.change_own_admin_password(
            admin_id,
            current_password="InitialPassword123!",
            new_password=new_password,
            confirm_password=confirmation,
        )

    assert (
        admin_rbac_service.get_my_admin_access(
            admin_id
        )["must_change_password"]
        is True
    )


def test_existing_administrator_not_forced_to_change_password(
    roles_env,
):
    ids, _ = roles_env

    admin_rbac_service.bootstrap_initial_super_admin(
        "owner.rbac@example.test"
    )

    access = admin_rbac_service.get_my_admin_access(
        ids["owner"]
    )

    assert access["must_change_password"] is False
    assert access["credential_version"] == 0
