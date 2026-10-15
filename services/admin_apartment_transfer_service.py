
"""Blue Moon Apartments — secure apartment transfer operations.

Transfers are immediate and preserve historical lease and payment records.
The resident's existing rent and deposit are carried forward.
"""

from datetime import date, timedelta

from sqlalchemy import func, select, update

from database.db import get_db_session
from database.models import (
    Apartment,
    ApartmentTransfer,
    Lease,
    MoveOutInspection,
    Notification,
    User,
)
from services.admin_moveout_inspection_service import (
    register_pending_inspection,
)

from services.admin_management_service import (
    _claim_vacant_apartment,
    _require_admin,
    _sync_occupancy,
)


# ==========================================================
# VALIDATION
# ==========================================================

def _validate_reason(reason: str) -> str:
    cleaned = (reason or "").strip()

    if len(cleaned) < 10:
        raise ValueError(
            "Transfer reason must contain "
            "at least 10 characters."
        )

    if len(cleaned) > 2000:
        raise ValueError(
            "Transfer reason must not exceed "
            "2,000 characters."
        )

    return cleaned


# ==========================================================
# ACTIVE RESIDENT LEASES
# ==========================================================

def get_transfer_candidates(
    admin_user_id: int,
) -> list[dict]:
    """Return residents with currently active leases."""

    today = date.today()

    with get_db_session() as db:
        _require_admin(db, admin_user_id, permission="leases.read")

        rows = db.execute(
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
                "lease_start": lease.start_date,
                "lease_end": lease.end_date,
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
# AVAILABLE DESTINATION APARTMENTS
# ==========================================================

def get_transfer_destinations(
    admin_user_id: int,
) -> list[dict]:
    """
    List vacant apartments with no recorded resident
    assignment or outstanding lease reservation.

    The write service rechecks all conditions.
    """

    today = date.today()

    with get_db_session() as db:
        _require_admin(db, admin_user_id, permission="apartments.read")

        assigned_ids = set(
            db.scalars(
                select(User.apartment_id).where(
                    User.apartment_id.is_not(None),
                    func.lower(User.role) == "resident",
                )
            ).all()
        )

        reserved_ids = set(
            db.scalars(
                select(Lease.apartment_id).where(
                    func.lower(Lease.status).in_(
                        [
                            "active",
                            "pending",
                            "scheduled",
                            "renewal_pending",
                        ]
                    ),
                    Lease.end_date >= today,
                )
            ).all()
        )

        apartments = db.scalars(
            select(Apartment)
            .where(
                Apartment.is_occupied.is_(False)
            )
            .order_by(Apartment.unit_number)
        ).all()

        inspection_hold_ids = set(
            db.scalars(
                select(MoveOutInspection.apartment_id)
                .where(
                    MoveOutInspection.status.in_(
                        ["pending", "inspected"]
                    )
                )
            ).all()
        )


        return [
            {
                "id": apartment.id,
                "unit": apartment.unit_number,
                "floor": apartment.floor,
                "bedrooms": apartment.bedrooms,
                "bathrooms": float(
                    apartment.bathrooms
                ),
                "listed_rent": float(
                    apartment.monthly_rent
                ),
            }
            for apartment in apartments
            if (
                apartment.id not in assigned_ids
                and apartment.id not in reserved_ids
                and apartment.id not in inspection_hold_ids
            )
        ]


# ==========================================================
# TRANSFER RESIDENT
# ==========================================================

def transfer_resident(
    admin_user_id: int,
    lease_id: int,
    *,
    expected_apartment_id: int,
    expected_end_date: date,
    new_apartment_id: int,
    reason: str,
) -> int:
    """
    Transfer a resident to a vacant apartment today.

    Existing lease:
        status becomes "transferred";
        actual final occupancy date is recorded.

    New lease:
        status "active";
        starts today;
        preserves the original lease expiration;
        carries forward existing rent and deposit.

    All updates and audit records are transactional.
    """

    cleaned_reason = _validate_reason(reason)

    if new_apartment_id == expected_apartment_id:
        raise ValueError(
            "Select a different apartment "
            "for the transfer."
        )

    if not isinstance(expected_end_date, date):
        raise ValueError(
            "Invalid expected lease expiration date."
        )

    today = date.today()

    with get_db_session() as db:

        _require_admin(
            db,
            admin_user_id,
            permission="transfers.execute",
        )

        # --------------------------------------
        # VERIFY CURRENT LEASE
        # --------------------------------------

        lease = db.get(
            Lease,
            lease_id,
        )

        if lease is None:
            raise ValueError(
                "Lease not found."
            )

        if str(lease.status or "").lower() != "active":
            raise ValueError(
                "Only active leases can be transferred."
            )

        if not lease.start_date <= today <= lease.end_date:
            raise ValueError(
                "The lease must currently be in effect."
            )

        if (
            lease.apartment_id != expected_apartment_id
            or lease.end_date != expected_end_date
        ):
            raise ValueError(
                "The current lease has changed. "
                "Refresh the page and try again."
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
                "Resident account is unavailable "
                "or inactive."
            )

        if resident.apartment_id != expected_apartment_id:
            raise ValueError(
                "Resident's current apartment assignment "
                "does not match the lease."
            )

        # Reject an inconsistent resident who has
        # multiple current or future active leases.

        another_active_lease = db.scalar(
            select(Lease.id).where(
                Lease.resident_id == resident.id,
                Lease.id != lease.id,
                func.lower(Lease.status) == "active",
                Lease.end_date >= today,
            ).limit(1)
        )

        if another_active_lease is not None:
            raise ValueError(
                "The resident has another active lease. "
                "Resolve duplicate lease records first."
            )

        old_apartment = db.get(
            Apartment,
            expected_apartment_id,
        )

        if old_apartment is None:
            raise ValueError(
                "Current apartment was not found."
            )

        # --------------------------------------
        # CHECK FUTURE TARGET LEASE CONFLICTS
        # --------------------------------------

        future_conflict = db.scalar(
            select(Lease.id).where(
                Lease.apartment_id == new_apartment_id,
                func.lower(Lease.status).in_(
                    [
                        "active",
                        "pending",
                        "scheduled",
                        "renewal_pending",
                    ]
                ),
                Lease.start_date <= expected_end_date,
                Lease.end_date >= today,
            ).limit(1)
        )

        if future_conflict is not None:
            raise ValueError(
                "The destination apartment already "
                "has a lease reservation overlapping "
                "the proposed transfer period."
            )

        # --------------------------------------
        # RESERVE VACANT DESTINATION
        # --------------------------------------

        new_apartment = _claim_vacant_apartment(
            db,
            new_apartment_id,
        )

        # Snapshot the original lease terms BEFORE
        # changing the current lease.

        original_end_date = lease.end_date
        current_rent = lease.monthly_rent
        current_deposit = lease.security_deposit or 0

        # If transferred on the lease start date,
        # keep that one-day historical record.
        # Otherwise end the old occupancy yesterday.

        previous_unit_last_date = max(
            lease.start_date,
            today - timedelta(days=1),
        )

        # --------------------------------------
        # CLOSE PREVIOUS LEASE
        # --------------------------------------

        lease_result = db.execute(
            update(Lease)
            .where(
                Lease.id == lease.id,
                Lease.apartment_id == expected_apartment_id,
                Lease.end_date == expected_end_date,
                func.lower(Lease.status) == "active",
            )
            .values(
                status="transferred",
                end_date=previous_unit_last_date,
            )
        )

        if lease_result.rowcount != 1:
            raise ValueError(
                "The original lease changed during "
                "this transfer. Refresh and retry."
            )

        # --------------------------------------
        # MOVE RESIDENT ACCOUNT
        # --------------------------------------

        resident_result = db.execute(
            update(User)
            .where(
                User.id == resident.id,
                User.apartment_id == expected_apartment_id,
                User.is_active.is_(True),
            )
            .values(
                apartment_id=new_apartment_id,
            )
        )

        if resident_result.rowcount != 1:
            raise ValueError(
                "The resident's apartment assignment "
                "changed during this transfer."
            )

        # --------------------------------------
        # CREATE NEW ACTIVE LEASE
        # --------------------------------------

        new_lease = Lease(
            resident_id=resident.id,
            apartment_id=new_apartment_id,
            start_date=today,
            end_date=original_end_date,
            monthly_rent=current_rent,
            security_deposit=current_deposit,
            status="active",
        )

        db.add(
            new_lease
        )

        db.flush()

        # --------------------------------------
        # SAVE AUDIT RECORD
        # --------------------------------------

        transfer = ApartmentTransfer(
            resident_id=resident.id,
            admin_user_id=admin_user_id,
            previous_apartment_id=old_apartment.id,
            new_apartment_id=new_apartment.id,
            previous_unit_number=old_apartment.unit_number,
            new_unit_number=new_apartment.unit_number,
            previous_lease_id=lease.id,
            new_lease_id=new_lease.id,
            effective_date=today,
            previous_contract_end_date=original_end_date,
            monthly_rent=current_rent,
            security_deposit=current_deposit,
            reason=cleaned_reason,
        )

        db.add(
            transfer
        )

        # --------------------------------------
        # NOTIFY RESIDENT
        # --------------------------------------

        db.add(
            Notification(
                user_id=resident.id,
                title="Apartment Transfer Completed",
                message=(
                    f"Your apartment assignment has "
                    f"changed from Unit "
                    f"{old_apartment.unit_number} to "
                    f"Unit {new_apartment.unit_number}, "
                    f"effective {today:%B %d, %Y}. "
                    f"Your current monthly rent remains "
                    f"${current_rent:,.2f}, and your "
                    f"lease expires on "
                    f"{original_end_date:%B %d, %Y}."
                ),
                notification_type="lease",
                is_read=False,
                is_alert=False,
            )
        )

        db.flush()

                # --------------------------------------
        # OLD APARTMENT NEEDS INSPECTION
        # --------------------------------------

        register_pending_inspection(
            db,
            apartment_id=old_apartment.id,
            resident_id=resident.id,
            lease_id=lease.id,
            initiated_by=admin_user_id,
            source="transfer",
        )

        # --------------------------------------
        # UPDATE BOTH OCCUPANCY FLAGS
        # --------------------------------------

        _sync_occupancy(
            db,
            {
                old_apartment.id,
                new_apartment.id,
            },
        )

        db.flush()

        return transfer.id


# ==========================================================
# TRANSFER AUDIT HISTORY
# ==========================================================

def get_apartment_transfer_history(
    admin_user_id: int,
    limit: int = 100,
) -> list[dict]:

    with get_db_session() as db:
        _require_admin(db, admin_user_id, permission="history.read")

        records = db.scalars(
            select(ApartmentTransfer)
            .order_by(
                ApartmentTransfer.created_at.desc(),
                ApartmentTransfer.id.desc(),
            )
            .limit(
                max(1, min(limit, 500))
            )
        ).all()

        history = []

        for item in records:

            resident = db.get(
                User,
                item.resident_id,
            )

            history.append(
                {
                    "transfer_id": item.id,
                    "resident": (
                        resident.full_name
                        if resident
                        else f"Resident #{item.resident_id}"
                    ),
                    "old_unit": item.previous_unit_number,
                    "new_unit": item.new_unit_number,
                    "effective_date": item.effective_date,
                    "contract_end": item.previous_contract_end_date,
                    "monthly_rent": float(
                        item.monthly_rent
                    ),
                    "reason": item.reason,
                    "admin_id": item.admin_user_id,
                    "created_at": item.created_at,
                }
            )

        return history
