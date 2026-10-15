
"""SQLAlchemy models for Blue Moon Apartments.

Store UTC timestamps as naive datetime values for compatibility with the
existing SQLite schema and current application services. No schema changes.
"""

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, Text, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# ==========================================================
# UTC TIMESTAMP HELPER
# ==========================================================

def utc_now() -> datetime:
    """
    Return the current UTC time without tzinfo.

    This preserves our existing database convention
    while avoiding the deprecated datetime.utcnow().
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ==========================================================
# SQLALCHEMY BASE
# ==========================================================

class Base(DeclarativeBase):
    pass


# ==========================================================
# APARTMENTS
# ==========================================================

class Apartment(Base):
    __tablename__ = "apartments"

    id: Mapped[int] = mapped_column(primary_key=True)

    unit_number: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False, index=True
    )

    floor: Mapped[int | None] = mapped_column(nullable=True)

    bedrooms: Mapped[int] = mapped_column(default=1)

    bathrooms: Mapped[Decimal] = mapped_column(
        Numeric(3, 1), default=1
    )

    monthly_rent: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False
    )

    is_occupied: Mapped[bool] = mapped_column(
        Boolean, default=False
    )

    residents: Mapped[list["User"]] = relationship(
        back_populates="apartment"
    )

    leases: Mapped[list["Lease"]] = relationship(
        back_populates="apartment"
    )

    maintenance_requests: Mapped[list["MaintenanceRequest"]] = relationship(
        back_populates="apartment"
    )


# ==========================================================
# USERS
# ==========================================================

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    first_name: Mapped[str] = mapped_column(
        String(100), nullable=False
    )

    last_name: Mapped[str] = mapped_column(
        String(100), nullable=False
    )

    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )

    password_hash: Mapped[str] = mapped_column(
        String(255), nullable=False
    )

    phone: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )

    role: Mapped[str] = mapped_column(
        String(30), default="resident"
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True
    )

    apartment_id: Mapped[int | None] = mapped_column(
        ForeignKey("apartments.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now
    )

    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    apartment: Mapped["Apartment | None"] = relationship(
        back_populates="residents"
    )

    leases: Mapped[list["Lease"]] = relationship(
        back_populates="resident"
    )

    payments: Mapped[list["Payment"]] = relationship(
        back_populates="resident"
    )

    login_events: Mapped[list["LoginEvent"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan"
    )

    notifications: Mapped[list["Notification"]] = relationship(
        back_populates="user"
    )

    maintenance_requests: Mapped[list["MaintenanceRequest"]] = relationship(
        back_populates="resident"
    )

    resident_profile: Mapped["ResidentProfile | None"] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan"
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


# ==========================================================
# LEASES
# ==========================================================

class Lease(Base):
    __tablename__ = "leases"

    id: Mapped[int] = mapped_column(primary_key=True)

    resident_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )

    apartment_id: Mapped[int] = mapped_column(
        ForeignKey("apartments.id"), nullable=False
    )

    start_date: Mapped[date] = mapped_column(
        Date, nullable=False
    )

    end_date: Mapped[date] = mapped_column(
        Date, nullable=False
    )

    monthly_rent: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False
    )

    security_deposit: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=0
    )

    status: Mapped[str] = mapped_column(
        String(30), default="active"
    )

    resident: Mapped["User"] = relationship(
        back_populates="leases"
    )

    apartment: Mapped["Apartment"] = relationship(
        back_populates="leases"
    )

    payments: Mapped[list["Payment"]] = relationship(
        back_populates="lease"
    )


# ==========================================================
# PAYMENTS
# ==========================================================

class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)

    resident_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )

    lease_id: Mapped[int | None] = mapped_column(
        ForeignKey("leases.id"), nullable=True
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False
    )

    payment_month: Mapped[date] = mapped_column(
        Date, nullable=False, index=True
    )

    payment_method: Mapped[str] = mapped_column(
        String(100), nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(30), default="confirmed"
    )

    confirmation_number: Mapped[str] = mapped_column(
        String(60), unique=True, nullable=False, index=True
    )

    paid_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now
    )

    resident: Mapped["User"] = relationship(
        back_populates="payments"
    )

    lease: Mapped["Lease | None"] = relationship(
        back_populates="payments"
    )


# ==========================================================
# NOTIFICATIONS
# ==========================================================

class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )

    title: Mapped[str] = mapped_column(
        String(255), nullable=False
    )

    message: Mapped[str] = mapped_column(
        String(1000), nullable=False
    )

    notification_type: Mapped[str] = mapped_column(
        String(50), default="general"
    )

    is_read: Mapped[bool] = mapped_column(
        Boolean, default=False
    )

    is_alert: Mapped[bool] = mapped_column(
        Boolean, default=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now
    )

    user: Mapped["User"] = relationship(
        back_populates="notifications"
    )


# ==========================================================
# MAINTENANCE REQUESTS
# ==========================================================

class MaintenanceRequest(Base):
    __tablename__ = "maintenance_requests"

    id: Mapped[int] = mapped_column(primary_key=True)

    request_number: Mapped[str] = mapped_column(
        String(30), unique=True, nullable=False, index=True
    )

    resident_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )

    apartment_id: Mapped[int] = mapped_column(
        ForeignKey("apartments.id"), nullable=False
    )

    category: Mapped[str] = mapped_column(
        String(100), nullable=False
    )

    location_detail: Mapped[str | None] = mapped_column(
        String(150), nullable=True
    )

    description: Mapped[str] = mapped_column(
        Text, nullable=False
    )

    urgency: Mapped[str] = mapped_column(
        String(30), nullable=False, default="Medium"
    )

    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="Submitted"
    )

    technician_name: Mapped[str | None] = mapped_column(
        String(150), nullable=True
    )

    scheduled_start: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    scheduled_end: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now
    )

    resident: Mapped["User"] = relationship(
        back_populates="maintenance_requests"
    )

    apartment: Mapped["Apartment"] = relationship(
        back_populates="maintenance_requests"
    )

    updates: Mapped[list["MaintenanceUpdate"]] = relationship(
        back_populates="request",
        cascade="all, delete-orphan"
    )


# ==========================================================
# ANNOUNCEMENTS
# ==========================================================

class Announcement(Base):
    __tablename__ = "announcements"

    id: Mapped[int] = mapped_column(primary_key=True)

    title: Mapped[str] = mapped_column(
        String(255), nullable=False
    )

    message: Mapped[str] = mapped_column(
        Text, nullable=False
    )

    category: Mapped[str] = mapped_column(
        String(100), nullable=False, default="General"
    )

    priority: Mapped[str] = mapped_column(
        String(30), nullable=False, default="Normal"
    )

    is_published: Mapped[bool] = mapped_column(
        Boolean, default=True
    )

    published_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now
    )

    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now
    )


# ==========================================================
# COMMUNITY NEWS
# ==========================================================

class CommunityNews(Base):
    __tablename__ = "community_news"

    id: Mapped[int] = mapped_column(primary_key=True)

    title: Mapped[str] = mapped_column(
        String(255), nullable=False
    )

    summary: Mapped[str] = mapped_column(
        Text, nullable=False
    )

    category: Mapped[str] = mapped_column(
        String(100), nullable=False, default="Community"
    )

    source_name: Mapped[str | None] = mapped_column(
        String(150), nullable=True
    )

    source_url: Mapped[str | None] = mapped_column(
        String(1000), nullable=True
    )

    published_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now
    )


# ==========================================================
# MAINTENANCE UPDATES / HISTORY
# ==========================================================

class MaintenanceUpdate(Base):
    __tablename__ = "maintenance_updates"

    id: Mapped[int] = mapped_column(primary_key=True)

    request_id: Mapped[int] = mapped_column(
        ForeignKey("maintenance_requests.id"),
        nullable=False,
        index=True
    )

    status: Mapped[str] = mapped_column(
        String(30), nullable=False
    )

    message: Mapped[str] = mapped_column(
        Text, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now
    )

    request: Mapped["MaintenanceRequest"] = relationship(
        back_populates="updates"
    )


# ==========================================================
# RESIDENT PROFILES
# ==========================================================

class ResidentProfile(Base):
    __tablename__ = "resident_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        unique=True,
        nullable=False,
        index=True
    )

    # Additional resident contact information

    secondary_email: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )

    secondary_phone: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )

    # Emergency contact information

    emergency_contact_name: Mapped[str | None] = mapped_column(
        String(150), nullable=True
    )

    emergency_contact_phone: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )

    preferred_contact_method: Mapped[str] = mapped_column(
        String(30), nullable=False, default="Email"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now
    )

    user: Mapped["User"] = relationship(
        back_populates="resident_profile"
    )


# ==========================================================
# LOGIN EVENTS
# ==========================================================

class LoginEvent(Base):
    __tablename__ = "login_events"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )

    event_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="login_success"
    )

    success: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )

    device_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )

    browser_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )

    ip_address: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )

    location_label: Mapped[str | None] = mapped_column(
        String(150), nullable=True
    )

    user_agent: Mapped[str | None] = mapped_column(
        String(1000), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now
    )

    user: Mapped["User"] = relationship(
        back_populates="login_events"
    )


# ==========================================================
# ADMIN EMPLOYEES
# ==========================================================

class AdminEmployee(Base):
    """Employee identity associated with an administrator account."""

    __tablename__ = "admin_employees"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        unique=True,
        nullable=False,
        index=True
    )

    employee_id: Mapped[str] = mapped_column(
        String(30),
        unique=True,
        nullable=False,
        index=True
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )

# ==========================================================
# TENANCY EVENTS / AUDIT HISTORY
# ==========================================================

class TenancyEvent(Base):
    """
    Record lease terminations and resident archiving.

    Historical lease and resident records are preserved.
    """

    __tablename__ = "tenancy_events"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    resident_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    lease_id: Mapped[int | None] = mapped_column(
        ForeignKey("leases.id"),
        nullable=True,
    )

    apartment_id: Mapped[int | None] = mapped_column(
        ForeignKey("apartments.id"),
        nullable=True,
    )

    admin_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    event_type: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
    )

    effective_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    original_lease_end_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
    )


# ==========================================================
# LEASE RENEWAL HISTORY
# ==========================================================

class LeaseRenewal(Base):
    """
    Audit record for an extension to an existing lease.

    The original and updated expiration dates are stored
    so each renewal can be reviewed later.
    """

    __tablename__ = "lease_renewals"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    lease_id: Mapped[int] = mapped_column(
        ForeignKey("leases.id"),
        nullable=False,
        index=True,
    )

    resident_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    apartment_id: Mapped[int] = mapped_column(
        ForeignKey("apartments.id"),
        nullable=False,
    )

    admin_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    previous_end_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    new_end_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    monthly_rent: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    notes: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
    )


# ==========================================================
# APARTMENT TRANSFER HISTORY
# ==========================================================

class ApartmentTransfer(Base):
    """Audit record of an apartment transfer."""

    __tablename__ = "apartment_transfers"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    resident_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    admin_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    previous_apartment_id: Mapped[int] = mapped_column(
        ForeignKey("apartments.id"),
        nullable=False,
    )

    new_apartment_id: Mapped[int] = mapped_column(
        ForeignKey("apartments.id"),
        nullable=False,
    )

    previous_unit_number: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    new_unit_number: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    previous_lease_id: Mapped[int] = mapped_column(
        ForeignKey("leases.id"),
        nullable=False,
    )

    new_lease_id: Mapped[int] = mapped_column(
        ForeignKey("leases.id"),
        nullable=False,
    )

    effective_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    previous_contract_end_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    monthly_rent: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    security_deposit: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
    )


# ==========================================================
# MOVE-OUT INSPECTION AND APARTMENT RELEASE
# ==========================================================

class MoveOutInspection(Base):
    """
    Track apartment turnover after a move-out or transfer.

    Status flow:
        pending -> inspected -> approved

    Pending and inspected records prevent new assignments.
    """

    __tablename__ = "move_out_inspections"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    apartment_id: Mapped[int] = mapped_column(
        ForeignKey("apartments.id"),
        nullable=False,
        index=True,
    )

    resident_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    lease_id: Mapped[int | None] = mapped_column(
        ForeignKey("leases.id"),
        nullable=True,
    )

    initiated_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    source: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending",
    )

    inspection_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    cleanliness: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    walls_floors: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    appliances: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    keys_returned: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    access_secured: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    repairs_completed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    damage_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    inspection_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    estimated_repair_cost: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=0,
    )

    inspected_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    approved_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
    )

    inspected_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )


# Database-level protection for SQLite:
# Only one unfinished inspection per apartment.
# Completed inspections remain as historical records.

Index(
    "uq_open_moveout_inspection_per_apartment",
    MoveOutInspection.apartment_id,
    unique=True,
    sqlite_where=MoveOutInspection.status.in_(
        ["pending", "inspected"]
    ),
)


# ==========================================================
# SECURITY DEPOSIT SETTLEMENT
# ==========================================================

class DepositSettlement(Base):
    """One security deposit settlement per lease."""

    __tablename__ = "deposit_settlements"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    lease_id: Mapped[int] = mapped_column(
        ForeignKey("leases.id"),
        unique=True,
        nullable=False,
        index=True,
    )

    resident_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    apartment_id: Mapped[int] = mapped_column(
        ForeignKey("apartments.id"),
        nullable=False,
    )

    deposit_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    approved_deductions: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=0,
    )

    approved_refund: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=0,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="draft",
    )

    notes: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    approved_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    refund_recorded_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    refund_method: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )

    refund_reference: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
    )

    refunded_on: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utc_now,
    )

    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )


# ==========================================================
# ITEMIZED DEPOSIT DEDUCTIONS
# ==========================================================

class DepositDeduction(Base):
    """A documented, proposed deduction."""

    __tablename__ = "deposit_deductions"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    settlement_id: Mapped[int] = mapped_column(
        ForeignKey("deposit_settlements.id"),
        nullable=False,
        index=True,
    )

    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utc_now,
    )


# ==========================================================
# DEPOSIT SETTLEMENT AUDIT EVENTS
# ==========================================================

class DepositSettlementEvent(Base):
    """Audit log for deposit settlement changes."""

    __tablename__ = "deposit_settlement_events"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    settlement_id: Mapped[int] = mapped_column(
        ForeignKey("deposit_settlements.id"),
        nullable=False,
        index=True,
    )

    admin_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    action: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
    )

    details: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utc_now,
    )


# ==========================================================
# ADMINISTRATOR ROLES — ADDITIVE RBAC TABLES
# ==========================================================

class AdminRoleAssignment(Base):
    """One application role per existing administrator account."""

    __tablename__ = "admin_role_assignments"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        unique=True,
        nullable=False,
        index=True,
    )

    role: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
    )

    assigned_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class AdminRoleChangeEvent(Base):
    """Append-only role assignment audit history."""

    __tablename__ = "admin_role_change_events"

    id: Mapped[int] = mapped_column(primary_key=True)

    actor_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    target_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    previous_role: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )

    new_role: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
    )

    action: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
    )

    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
    )


# ==========================================================
# SPRINT 11B.4 — ADMINISTRATOR CREDENTIAL STATE
# ==========================================================

class AdminCredentialState(Base):
    """
    Persistent password security state for administrators.

    Existing administrators without a row are treated
    as legacy accounts that do not need an initial
    password change.

    credential_version is used to revoke older sessions
    after password or credential-security changes.
    """

    __tablename__ = "admin_credential_states"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        primary_key=True,
    )

    must_change_password: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    credential_version: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
    )

    # Reserved for the one-time reset-code workflow
    # in Sprint 11B.4B.

    reset_token_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    reset_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


# ==========================================================
# SPRINT 11B.5 — AUTHENTICATION FAILURE TRACKING
# ==========================================================

class AuthenticationFailureAttempt(Base):
    """
    Records failed authentication attempts.

    Raw email addresses, employee IDs, passwords,
    and reset codes are never stored here.

    The table supports rolling-window rate limits
    for resident login, admin login, and reset codes.
    """

    __tablename__ = "authentication_failure_attempts"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    identity_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )

    flow: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utc_now,
    )

    __table_args__ = (
        Index(
            "ix_auth_failures_flow_identity_time",
            "flow",
            "identity_hash",
            "created_at",
        ),
    )


# ==========================================================
# SPRINT 11B.6D — OFFLINE EMERGENCY RECOVERY AUDIT
# ==========================================================

class EmergencySuperAdminRecoveryEvent(Base):
    """Permanent record of an offline Super Admin recovery.

    An emergency key fingerprint is unique, preventing
    the same configured recovery key from being used twice.
    """

    __tablename__ = "emergency_super_admin_recovery_events"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    target_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    key_fingerprint: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
    )

    operator_label: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    ticket_reference: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
    )

    reason: Mapped[str] = mapped_column(
        String(300),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utc_now,
    )

