
"""Blue Moon Apartments — secure lease extension service."""

from datetime import date, datetime, timedelta

from sqlalchemy import func, select, update

from database.db import get_db_session
from database.models import (
    Apartment,
    Lease,
    LeaseRenewal,
    Notification,
    User,
)

from services.admin_management_service import _require_admin


# ==========================================================
# VALIDATION HELPERS
# ==========================================================

def _require_calendar_date(value: date, label: str) -> None:
    if (
        not isinstance(value, date)
        or isinstance(value, datetime)
    ):
        raise ValueError(
            f"{label} must be a valid calendar date."
        )


def _validate_notes(notes: str) -> str:
    cleaned = (notes or "").strip()

    if len(cleaned) < 10:
        raise ValueError(
            "Please enter renewal notes containing "
            "at least 10 characters."
        )

    if len(cleaned) > 2000:
        raise ValueError(
            "Renewal notes cannot exceed 2,000 characters."
        )

    return cleaned


# ==========================================================
# VIEW ELIGIBLE ACTIVE LEASES
# ==========================================================

def get_renewable_leases(admin_user_id: int) -> list[dict]:
    """
    Return currently active, correctly assigned leases.

    Lease extensions do not reassign apartments.
    """

    today = date.today()

    with get_db_session() as db:
        _require_admin(db, admin_user_id, permission="leases.read")

        records = db.execute(
            select(Lease, User, Apartment)
            .join(User, Lease.resident_id == User.id)
            .join(
                Apartment,
                Lease.apartment_id == Apartment.id,
            )
            .where(
                func.lower(Lease.status) == "active",
                Lease.start_date <= today,
                Lease.end_date >= today,
                func.lower(User.role) == "resident",
                User.is_active.is_(True),
                User.apartment_id == Lease.apartment_id,
            )
            .order_by(
                User.last_name,
                User.first_name,
                Apartment.unit_number,
            )
        ).all()

        return [
            {
                "lease_id": lease.id,
                "resident_id": resident.id,
                "resident_name": resident.full_name,
                "email": resident.email,
                "apartment_id": apartment.id,
                "unit": apartment.unit_number,
                "start_date": lease.start_date,
                "end_date": lease.end_date,
                "monthly_rent": float(lease.monthly_rent),
                "security_deposit": float(
                    lease.security_deposit or 0
                ),
            }
            for lease, resident, apartment in records
        ]


# ==========================================================
# EXTEND AN EXISTING ACTIVE LEASE
# ==========================================================

def renew_lease(
    admin_user_id: int,
    lease_id: int,
    *,
    expected_end_date: date,
    new_end_date: date,
    notes: str,
) -> int:
    """
    Extend an active lease without changing its rent.

    The renewal operation:
    - Verifies administrator authorization.
    - Verifies lease and resident eligibility.
    - Prevents shortening or duplicating a renewal.
    - Rejects overlapping future leases for the unit.
    - Updates the existing lease expiration date.
    - Writes a historical renewal record.
    - Notifies the resident.

    All changes are in one database transaction.
    """

    _require_calendar_date(
        expected_end_date,
        "Current lease end date",
    )

    _require_calendar_date(
        new_end_date,
        "New lease end date",
    )

    cleaned_notes = _validate_notes(notes)

    with get_db_session() as db:
        _require_admin(db, admin_user_id, permission="leases.renew")

        lease = db.get(
            Lease,
            lease_id,
        )

        if lease is None:
            raise ValueError(
                "Lease not found."
            )

        today = date.today()

        if str(lease.status or "").lower() != "active":
            raise ValueError(
                "Only active leases can be renewed."
            )

        if not lease.start_date <= today <= lease.end_date:
            raise ValueError(
                "The lease must currently be in effect."
            )

        if lease.end_date != expected_end_date:
            raise ValueError(
                "The lease end date has changed since "
                "you opened this form. Refresh and try again."
            )

        if new_end_date <= lease.end_date:
            raise ValueError(
                "The new end date must be later "
                "than the current lease end date."
            )

        resident = db.get(
            User,
            lease.resident_id,
        )

        if (
            resident is None
            or not resident.is_active
            or str(resident.role or "").lower() != "resident"
        ):
            raise ValueError(
                "The resident account is inactive "
                "or unavailable."
            )

        if resident.apartment_id != lease.apartment_id:
            raise ValueError(
                "The resident's apartment assignment "
                "does not match this lease."
            )

        apartment = db.get(
            Apartment,
            lease.apartment_id,
        )

        if apartment is None:
            raise ValueError(
                "The leased apartment was not found."
            )

        # ------------------------------------------
        # PREVENT OVERLAPPING FUTURE LEASES
        # ------------------------------------------

        extension_start = (
            lease.end_date + timedelta(days=1)
        )

        conflicting_lease = db.scalar(
            select(Lease.id)
            .where(
                Lease.apartment_id == lease.apartment_id,
                Lease.id != lease.id,
                func.lower(Lease.status).in_(
                    [
                        "active",
                        "pending",
                        "scheduled",
                        "renewal_pending",
                    ]
                ),
                Lease.start_date <= new_end_date,
                Lease.end_date >= extension_start,
            )
            .limit(1)
        )

        if conflicting_lease is not None:
            raise ValueError(
                "Another lease overlaps the requested "
                "extension period. Resolve it first."
            )

        previous_end_date = lease.end_date

        # ------------------------------------------
        # ATOMIC UPDATE WITH STALE-DATA PROTECTION
        # ------------------------------------------

        result = db.execute(
            update(Lease)
            .where(
                Lease.id == lease_id,
                func.lower(Lease.status) == "active",
                Lease.end_date == previous_end_date,
            )
            .values(
                end_date=new_end_date,
            )
        )

        if result.rowcount != 1:
            raise ValueError(
                "This lease changed during the renewal. "
                "Refresh and try again."
            )

        # ------------------------------------------
        # SAVE AUDIT HISTORY
        # ------------------------------------------

        renewal = LeaseRenewal(
            lease_id=lease.id,
            resident_id=lease.resident_id,
            apartment_id=lease.apartment_id,
            admin_user_id=admin_user_id,
            previous_end_date=previous_end_date,
            new_end_date=new_end_date,
            monthly_rent=lease.monthly_rent,
            notes=cleaned_notes,
        )

        db.add(renewal)

        # ------------------------------------------
        # NOTIFY RESIDENT
        # ------------------------------------------

        db.add(
            Notification(
                user_id=resident.id,
                title="Lease Extension Recorded",
                message=(
                    f"Your lease for Unit "
                    f"{apartment.unit_number} has been "
                    f"extended through "
                    f"{new_end_date:%B %d, %Y}. "
                    "Your recorded monthly rent "
                    "has not changed."
                ),
                notification_type="lease",
                is_read=False,
                is_alert=False,
            )
        )

        db.flush()

        return renewal.id


# ==========================================================
# VIEW RENEWAL AUDIT HISTORY
# ==========================================================

def get_lease_renewal_history(
    admin_user_id: int,
    limit: int = 100,
) -> list[dict]:
    """Return recent recorded lease extensions."""

    with get_db_session() as db:
        _require_admin(db, admin_user_id, permission="history.read")

        records = db.scalars(
            select(LeaseRenewal)
            .order_by(
                LeaseRenewal.created_at.desc(),
                LeaseRenewal.id.desc(),
            )
            .limit(
                max(1, min(limit, 500))
            )
        ).all()

        result = []

        for item in records:
            resident = db.get(
                User,
                item.resident_id,
            )

            apartment = db.get(
                Apartment,
                item.apartment_id,
            )

            result.append(
                {
                    "renewal_id": item.id,
                    "resident": (
                        resident.full_name
                        if resident
                        else f"Resident #{item.resident_id}"
                    ),
                    "unit": (
                        apartment.unit_number
                        if apartment
                        else "Unknown"
                    ),
                    "previous_end": item.previous_end_date,
                    "new_end": item.new_end_date,
                    "monthly_rent": float(
                        item.monthly_rent
                    ),
                    "notes": item.notes,
                    "admin_id": item.admin_user_id,
                    "recorded_at": item.created_at,
                }
            )

        return result
