from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Apartment(Base):
    __tablename__ = "apartments"

    id: Mapped[int] = mapped_column(primary_key=True)

    unit_number: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        nullable=False,
        index=True,
    )

    floor: Mapped[int | None] = mapped_column(nullable=True)

    bedrooms: Mapped[int] = mapped_column(default=1)

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


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

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

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class Lease(Base):
    __tablename__ = "leases"

    id: Mapped[int] = mapped_column(primary_key=True)

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