from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    pass


class Apartment(Base):
    __tablename__ = "apartments"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    unit_number: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        nullable=False,
        index=True,
    )

    floor: Mapped[int | None] = mapped_column(
        nullable=True
    )

    bedrooms: Mapped[int] = mapped_column(
        default=1
    )

    bathrooms: Mapped[Decimal] = mapped_column(
        Numeric(3, 1),
        default=1,
    )

    monthly_rent: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    is_occupied: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    residents: Mapped[list["User"]] = relationship(
        back_populates="apartment"
    )

    leases: Mapped[list["Lease"]] = relationship(
        back_populates="apartment"
    )

    maintenance_requests: Mapped[
        list["MaintenanceRequest"]
    ] = relationship(
        back_populates="apartment"
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    first_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    last_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    phone: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    role: Mapped[str] = mapped_column(
        String(30),
        default="resident",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )

    apartment_id: Mapped[int | None] = mapped_column(
        ForeignKey("apartments.id"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
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

    login_events: Mapped[
        list["LoginEvent"]
    ] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    notifications: Mapped[
        list["Notification"]
    ] = relationship(
        back_populates="user"
    )

    maintenance_requests: Mapped[
        list["MaintenanceRequest"]
    ] = relationship(
        back_populates="resident"
    )

    resident_profile: Mapped[
        "ResidentProfile | None"
    ] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )

    @property
    def full_name(self) -> str:
        return (
            f"{self.first_name} "
            f"{self.last_name}"
        )


class Lease(Base):
    __tablename__ = "leases"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    resident_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    apartment_id: Mapped[int] = mapped_column(
        ForeignKey("apartments.id"),
        nullable=False,
    )

    start_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    end_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    monthly_rent: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    security_deposit: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        default=0,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="active",
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


class Payment(Base):
    __tablename__ = "payments"

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

    amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    payment_month: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    payment_method: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="confirmed",
    )

    confirmation_number: Mapped[str] = mapped_column(
        String(60),
        unique=True,
        nullable=False,
        index=True,
    )

    paid_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    resident: Mapped["User"] = relationship(
        back_populates="payments"
    )

    lease: Mapped["Lease | None"] = relationship(
        back_populates="payments"
    )


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    message: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
    )

    notification_type: Mapped[str] = mapped_column(
        String(50),
        default="general",
    )

    is_read: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    is_alert: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    user: Mapped["User"] = relationship(
        back_populates="notifications"
    )


class MaintenanceRequest(Base):
    __tablename__ = "maintenance_requests"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    request_number: Mapped[str] = mapped_column(
        String(30),
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

    category: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    location_detail: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    urgency: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="Medium",
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="Submitted",
    )

    technician_name: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    scheduled_start: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime,
        nullable=True,
    )

    scheduled_end: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    resident: Mapped["User"] = relationship(
        back_populates="maintenance_requests"
    )

    apartment: Mapped["Apartment"] = relationship(
        back_populates="maintenance_requests"
    )

    updates: Mapped[
        list["MaintenanceUpdate"]
    ] = relationship(
        back_populates="request",
        cascade="all, delete-orphan",
    )

class Announcement(Base):
    __tablename__ = "announcements"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    category: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="General",
    )

    priority: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="Normal",
    )

    is_published: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )

    published_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )


class CommunityNews(Base):
    __tablename__ = "community_news"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    category: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="Community",
    )

    source_name: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    source_url: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    published_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )



class MaintenanceUpdate(Base):
    __tablename__ = "maintenance_updates"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    request_id: Mapped[int] = mapped_column(
        ForeignKey("maintenance_requests.id"),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    request: Mapped[
        "MaintenanceRequest"
    ] = relationship(
        back_populates="updates"
    )

class ResidentProfile(Base):
    __tablename__ = "resident_profiles"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        unique=True,
        nullable=False,
        index=True,
    )

    emergency_contact_name: Mapped[
        str | None
    ] = mapped_column(
        String(150),
        nullable=True,
    )

    emergency_contact_phone: Mapped[
        str | None
    ] = mapped_column(
        String(30),
        nullable=True,
    )

    preferred_contact_method: Mapped[str] = (
        mapped_column(
            String(30),
            nullable=False,
            default="Email",
        )
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    user: Mapped["User"] = relationship(
        back_populates="resident_profile"
    )

class LoginEvent(Base):
    __tablename__ = "login_events"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="login_success",
    )

    success: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    device_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    browser_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    ip_address: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    location_label: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    user_agent: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    user: Mapped["User"] = relationship(
        back_populates="login_events"
    )