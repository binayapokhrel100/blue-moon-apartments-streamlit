
"""Blue Moon Apartments — Lease termination and tenant archiving.

Preserves historical data and creates inspection holds when
apartments are vacated.

Every write requires an active administrator employee.
"""

from datetime import date

from sqlalchemy import func, select, update
from sqlalchemy.orm import joinedload

from database.db import get_db_session

from database.models import (
    Apartment,
    Lease,
    TenancyEvent,
    User,
)

from services.admin_management_service import (
    _require_admin,
    _sync_occupancy,
)

from services.admin_moveout_inspection_service import (
    register_pending_inspection,
)


# ==========================================================
# VALIDATION HELPERS
# ==========================================================

def _clean_reason(reason: str) -> str:

    value = (reason or "").strip()

    if len(value) < 10:
        raise ValueError(
            "Please enter a reason containing "
            "at least 10 characters."
        )

    if len(value) > 2000:
        raise ValueError(
            "The reason must be 2,000 characters "
            "or fewer."
        )

    return value


def _get_resident(db, resident_id: int) -> User:

    resident = db.get(
        User,
        resident_id,
    )

    if (
        resident is None
        or str(resident.role or "").strip().lower()
        != "resident"
    ):
        raise ValueError(
            "Resident not found."
        )

    return resident


def _get_active_leases(
    db,
    resident_id: int,
) -> list[Lease]:

    today = date.today()

    return list(
        db.scalars(
            select(Lease).where(
                Lease.resident_id == resident_id,
                func.lower(Lease.status) == "active",
                Lease.end_date >= today,
            )
        ).all()
    )


# ==========================================================
# VIEW ACTIVE TENANCIES
# ==========================================================

def get_active_tenancies(
    admin_id: int,
) -> list[dict]:

    today = date.today()

    with get_db_session() as db:

        _require_admin(
            db,
            admin_id,
            permission="leases.read",
        )

        rows = db.execute(
            select(Lease, User, Apartment)
            .join(
                User,
                Lease.resident_id == User.id,
            )
            .join(
                Apartment,
                Lease.apartment_id == Apartment.id,
            )
            .where(
                func.lower(User.role) == "resident",
                User.is_active.is_(True),
                func.lower(Lease.status) == "active",
                Lease.start_date <= today,
                Lease.end_date >= today,
            )
            .order_by(
                User.last_name,
                User.first_name,
            )
        ).all()

        return [
            {
                "lease_id": lease.id,
                "resident_id": resident.id,
                "resident": resident.full_name,
                "email": resident.email,
                "unit": apartment.unit_number,
                "apartment_id": apartment.id,
                "start_date": lease.start_date,
                "end_date": lease.end_date,
                "monthly_rent": float(
                    lease.monthly_rent
                ),
                "security_deposit": float(
                    lease.security_deposit or 0
                ),
            }
            for lease, resident, apartment in rows
        ]


# ==========================================================
# VIEW RESIDENTS ELIGIBLE FOR ARCHIVING
# ==========================================================

def get_archive_candidates(
    admin_id: int,
) -> list[dict]:

    today = date.today()

    with get_db_session() as db:

        _require_admin(
            db,
            admin_id,
            permission="tenants.read",
        )

        active_lease_residents = set(
            db.scalars(
                select(Lease.resident_id).where(
                    func.lower(Lease.status) == "active",
                    Lease.end_date >= today,
                )
            ).all()
        )

        residents = db.scalars(
            select(User)
            .options(
                joinedload(User.apartment)
            )
            .where(
                func.lower(User.role) == "resident",
                User.is_active.is_(True),
            )
            .order_by(
                User.last_name,
                User.first_name,
            )
        ).all()

        return [
            {
                "resident_id": person.id,
                "name": person.full_name,
                "email": person.email,
                "unit": (
                    person.apartment.unit_number
                    if person.apartment
                    else "Unassigned"
                ),
                "apartment_id": person.apartment_id,
            }
            for person in residents
            if person.id not in active_lease_residents
        ]


# ==========================================================
# TERMINATE LEASE / COMPLETE MOVE-OUT
# ==========================================================

def terminate_lease_and_move_out(
    admin_id: int,
    resident_id: int,
    *,
    reason: str,
) -> None:
    """
    Immediately terminate an active lease and move out
    the resident.

    Creates exactly ONE pending inspection for the
    apartment being vacated.

    All changes are saved in a single transaction.
    """

    clean_reason = _clean_reason(
        reason
    )

    with get_db_session() as db:

        _require_admin(
            db,
            admin_id,
            permission="leases.terminate",
        )

        resident = _get_resident(
            db,
            resident_id,
        )

        if not resident.is_active:
            raise ValueError(
                "This resident account is already inactive."
            )

        active_leases = _get_active_leases(
            db,
            resident_id,
        )

        if not active_leases:
            raise ValueError(
                "This resident has no active lease "
                "to terminate."
            )

        if len(active_leases) != 1:
            raise ValueError(
                "Multiple active leases were found. "
                "Resolve the records before proceeding."
            )

        lease = active_leases[0]

        today = date.today()

        if lease.start_date > today:
            raise ValueError(
                "This lease has not started yet. "
                "Use a future cancellation workflow."
            )

        if resident.apartment_id != lease.apartment_id:
            raise ValueError(
                "Resident assignment does not match "
                "the lease apartment."
            )

        old_apartment_id = (
            resident.apartment_id
        )

        # --------------------------------------
        # TERMINATE EXISTING LEASE
        # --------------------------------------

        lease_result = db.execute(
            update(Lease)
            .where(
                Lease.id == lease.id,
                func.lower(Lease.status) == "active",
            )
            .values(
                status="terminated"
            )
        )

        if lease_result.rowcount != 1:
            raise ValueError(
                "The lease was changed by another action. "
                "Refresh and try again."
            )

        # --------------------------------------
        # DEACTIVATE RESIDENT / UNASSIGN UNIT
        # --------------------------------------

        account_result = db.execute(
            update(User)
            .where(
                User.id == resident.id,
                User.is_active.is_(True),
            )
            .values(
                is_active=False,
                apartment_id=None,
            )
        )

        if account_result.rowcount != 1:
            raise ValueError(
                "The resident account was changed. "
                "Refresh and try again."
            )

        # --------------------------------------
        # RECORD TERMINATION HISTORY
        # --------------------------------------

        db.add(
            TenancyEvent(
                resident_id=resident.id,
                lease_id=lease.id,
                apartment_id=old_apartment_id,
                admin_user_id=admin_id,
                event_type="lease_terminated",
                effective_date=today,
                original_lease_end_date=lease.end_date,
                reason=clean_reason,
            )
        )

        db.flush()

        # ======================================
        # CREATE EXACTLY ONE INSPECTION HOLD
        # ======================================

        register_pending_inspection(
            db,
            apartment_id=old_apartment_id,
            resident_id=resident.id,
            lease_id=lease.id,
            initiated_by=admin_id,
            source="move_out",
        )

        # --------------------------------------
        # REFRESH OCCUPANCY
        # --------------------------------------

        _sync_occupancy(
            db,
            {old_apartment_id},
        )


# ==========================================================
# ARCHIVE RESIDENT WITHOUT ACTIVE LEASE
# ==========================================================

def archive_resident(
    admin_id: int,
    resident_id: int,
    *,
    reason: str,
) -> None:
    """
    Archive a resident who has no unexpired active lease.

    If the resident had an apartment assignment,
    create one pending inspection for that apartment.

    An unassigned resident does not require inspection.
    Historical records are preserved.
    """

    clean_reason = _clean_reason(
        reason
    )

    with get_db_session() as db:

        _require_admin(
            db,
            admin_id,
            permission="tenants.archive",
        )

        resident = _get_resident(
            db,
            resident_id,
        )

        if not resident.is_active:
            raise ValueError(
                "Resident is already archived or inactive."
            )

        if _get_active_leases(
            db,
            resident_id,
        ):
            raise ValueError(
                "This resident has an active lease. "
                "Use Lease Termination / Move-Out first."
            )

        old_apartment_id = (
            resident.apartment_id
        )

        # --------------------------------------
        # DEACTIVATE ACCOUNT
        # --------------------------------------

        result = db.execute(
            update(User)
            .where(
                User.id == resident.id,
                User.is_active.is_(True),
            )
            .values(
                is_active=False,
                apartment_id=None,
            )
        )

        if result.rowcount != 1:
            raise ValueError(
                "The resident account was changed. "
                "Refresh and try again."
            )

        # --------------------------------------
        # RECORD ARCHIVE HISTORY
        # --------------------------------------

        db.add(
            TenancyEvent(
                resident_id=resident.id,
                lease_id=None,
                apartment_id=old_apartment_id,
                admin_user_id=admin_id,
                event_type="account_archived",
                effective_date=date.today(),
                original_lease_end_date=None,
                reason=clean_reason,
            )
        )

        db.flush()

        # ======================================
        # INSPECTION FOR AN ASSIGNED UNIT
        # ======================================

        if old_apartment_id is not None:

            register_pending_inspection(
                db,
                apartment_id=old_apartment_id,
                resident_id=resident.id,
                lease_id=None,
                initiated_by=admin_id,
                source="archive",
            )

        # --------------------------------------
        # REFRESH OCCUPANCY
        # --------------------------------------

        _sync_occupancy(
            db,
            {old_apartment_id},
        )


# ==========================================================
# TENANCY ACTIVITY HISTORY
# ==========================================================

def get_tenancy_history(
    admin_id: int,
    limit: int = 100,
) -> list[dict]:

    with get_db_session() as db:

        _require_admin(
            db,
            admin_id,
            permission="history.read",
        )

        records = db.scalars(
            select(TenancyEvent)
            .order_by(
                TenancyEvent.created_at.desc(),
                TenancyEvent.id.desc(),
            )
            .limit(
                max(1, min(limit, 500))
            )
        ).all()

        results = []

        for event in records:

            resident = db.get(
                User,
                event.resident_id,
            )

            apartment = (
                db.get(
                    Apartment,
                    event.apartment_id,
                )
                if event.apartment_id is not None
                else None
            )

            results.append(
                {
                    "date": event.effective_date,
                    "resident": (
                        resident.full_name
                        if resident
                        else f"Resident #{event.resident_id}"
                    ),
                    "apartment": (
                        apartment.unit_number
                        if apartment
                        else "—"
                    ),
                    "action": event.event_type,
                    "reason": event.reason,
                    "original_lease_end": (
                        event.original_lease_end_date
                    ),
                    "admin_id": event.admin_user_id,
                }
            )

        return results
