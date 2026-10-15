
"""Blue Moon Apartments — Move-Out Inspection Service.

An open inspection blocks apartment assignment.
Approval releases the hold but does not change financial records.
"""

from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select, update

from database.db import get_db_session
from database.models import (
    Apartment,
    Lease,
    MoveOutInspection,
    User,
    utc_now,
)
from services.admin_management_service import _require_admin


OPEN_STATUSES = ("pending", "inspected")

CONDITION_OPTIONS = (
    "Good",
    "Fair",
    "Needs Repair",
)


# ==========================================================
# INTERNAL: CREATE INSPECTION HOLD
# ==========================================================

def register_pending_inspection(
    db,
    *,
    apartment_id: int,
    resident_id: int,
    lease_id: int | None,
    initiated_by: int,
    source: str,
) -> int:
    """
    Called inside an existing admin transaction.

    Creates an inspection hold before releasing the unit.
    No separate database transaction is opened.
    """

    if source not in ("move_out", "transfer", "archive"):
        raise ValueError("Invalid inspection source.")

    existing = db.scalar(
        select(MoveOutInspection.id).where(
            MoveOutInspection.apartment_id == apartment_id,
            MoveOutInspection.status.in_(OPEN_STATUSES),
        ).limit(1)
    )

    if existing is not None:
        raise ValueError(
            "This apartment already has an unfinished "
            "inspection. Resolve it before continuing."
        )

    record = MoveOutInspection(
        apartment_id=apartment_id,
        resident_id=resident_id,
        lease_id=lease_id,
        initiated_by=initiated_by,
        source=source,
        status="pending",
    )

    db.add(record)
    db.flush()

    return record.id


# ==========================================================
# APARTMENTS BLOCKED BY INSPECTIONS
# ==========================================================

def get_blocked_apartment_ids(
    admin_user_id: int,
) -> set[int]:
    """Return units not yet approved for another tenant."""

    with get_db_session() as db:
        _require_admin(db, admin_user_id, permission="apartments.read")

        return set(
            db.scalars(
                select(MoveOutInspection.apartment_id)
                .where(
                    MoveOutInspection.status.in_(OPEN_STATUSES)
                )
            ).all()
        )


# ==========================================================
# OPEN INSPECTION QUEUE
# ==========================================================

def get_open_inspections(
    admin_user_id: int,
) -> list[dict]:

    with get_db_session() as db:
        _require_admin(db, admin_user_id, permission="inspections.read")

        rows = db.execute(
            select(MoveOutInspection, Apartment, User)
            .join(
                Apartment,
                MoveOutInspection.apartment_id == Apartment.id,
            )
            .join(
                User,
                MoveOutInspection.resident_id == User.id,
            )
            .where(
                MoveOutInspection.status.in_(OPEN_STATUSES)
            )
            .order_by(
                MoveOutInspection.created_at,
                MoveOutInspection.id,
            )
        ).all()

        return [
            {
                "id": item.id,
                "apartment_id": apartment.id,
                "unit": apartment.unit_number,
                "resident": resident.full_name,
                "resident_id": resident.id,
                "source": item.source,
                "status": item.status,
                "created_at": item.created_at,
                "inspection_date": item.inspection_date,
                "cleanliness": item.cleanliness,
                "walls_floors": item.walls_floors,
                "appliances": item.appliances,
                "keys_returned": item.keys_returned,
                "access_secured": item.access_secured,
                "repairs_completed": item.repairs_completed,
                "damage_notes": item.damage_notes or "",
                "inspection_notes": item.inspection_notes or "",
                "estimated_repair_cost": float(
                    item.estimated_repair_cost or 0
                ),
            }
            for item, apartment, resident in rows
        ]


# ==========================================================
# VALIDATE INSPECTION REPORT
# ==========================================================

def _validate_condition(
    value: str,
    field_name: str,
) -> str:

    if value not in CONDITION_OPTIONS:
        raise ValueError(
            f"Invalid {field_name} condition."
        )

    return value


def _validate_repair_cost(value: object) -> Decimal:

    try:
        cost = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(
            "Enter a valid repair estimate."
        ) from None

    if (
        not cost.is_finite()
        or cost < 0
        or cost > Decimal("99999999.99")
    ):
        raise ValueError(
            "Repair estimate must be between "
            "$0 and $99,999,999.99."
        )

    if cost != cost.quantize(Decimal("0.01")):
        raise ValueError(
            "Repair estimate cannot have more "
            "than two decimal places."
        )

    return cost


# ==========================================================
# RECORD OR REVISE INSPECTION
# ==========================================================

def record_inspection(
    admin_user_id: int,
    inspection_id: int,
    *,
    cleanliness: str,
    walls_floors: str,
    appliances: str,
    keys_returned: bool,
    access_secured: bool,
    repairs_completed: bool,
    damage_notes: str,
    inspection_notes: str,
    estimated_repair_cost: object = 0,
) -> None:
    """
    Record findings or update an inspection before approval.

    A revision is allowed while status is 'inspected',
    so completed repairs can be documented later.
    Approved records cannot be edited.
    """

    cleanliness = _validate_condition(
        cleanliness, "cleanliness"
    )
    walls_floors = _validate_condition(
        walls_floors, "walls/floors"
    )
    appliances = _validate_condition(
        appliances, "appliances"
    )

    notes = (inspection_notes or "").strip()
    damages = (damage_notes or "").strip()

    if not 10 <= len(notes) <= 2000:
        raise ValueError(
            "Inspection notes must contain "
            "10–2,000 characters."
        )

    if len(damages) > 2000:
        raise ValueError(
            "Damage notes must be "
            "2,000 characters or fewer."
        )

    cost = _validate_repair_cost(
        estimated_repair_cost
    )

    with get_db_session() as db:
        _require_admin(db, admin_user_id, permission="inspections.record")

        item = db.get(
            MoveOutInspection,
            inspection_id,
        )

        if item is None:
            raise ValueError(
                "Inspection not found."
            )

        if item.status not in OPEN_STATUSES:
            raise ValueError(
                "Approved inspections cannot be modified."
            )

        result = db.execute(
            update(MoveOutInspection)
            .where(
                MoveOutInspection.id == inspection_id,
                MoveOutInspection.status.in_(OPEN_STATUSES),
            )
            .values(
                status="inspected",
                inspection_date=date.today(),
                cleanliness=cleanliness,
                walls_floors=walls_floors,
                appliances=appliances,
                keys_returned=bool(keys_returned),
                access_secured=bool(access_secured),
                repairs_completed=bool(repairs_completed),
                damage_notes=damages,
                inspection_notes=notes,
                estimated_repair_cost=cost,
                inspected_by=admin_user_id,
                inspected_at=utc_now(),
            )
        )

        if result.rowcount != 1:
            raise ValueError(
                "The inspection changed. Refresh and retry."
            )


# ==========================================================
# APPROVE INSPECTION AND RELEASE APARTMENT
# ==========================================================

def approve_inspection(
    admin_user_id: int,
    inspection_id: int,
) -> None:
    """
    Release an apartment only after inspection approval.

    The apartment must:
      - Have a completed inspection report.
      - Have secured access.
      - Have necessary repairs completed.
      - Have no current assignment or lease reservation.
      - Be physically recorded as unoccupied.
    """

    today = date.today()

    with get_db_session() as db:
        _require_admin(db, admin_user_id, permission="inspections.approve")

        item = db.get(
            MoveOutInspection,
            inspection_id,
        )

        if item is None:
            raise ValueError(
                "Inspection not found."
            )

        if item.status != "inspected":
            raise ValueError(
                "Complete the inspection before approval."
            )

        if not item.access_secured:
            raise ValueError(
                "Apartment access must be secured "
                "before the unit can be released."
            )

        conditions = (
            item.cleanliness,
            item.walls_floors,
            item.appliances,
        )

        if (
            "Needs Repair" in conditions
            and not item.repairs_completed
        ):
            raise ValueError(
                "Complete required repairs before "
                "approving the inspection."
            )

        apartment = db.get(
            Apartment,
            item.apartment_id,
        )

        if apartment is None:
            raise ValueError(
                "Apartment not found."
            )

        if apartment.is_occupied:
            raise ValueError(
                "Apartment is currently marked occupied."
            )

        assigned = db.scalar(
            select(User.id).where(
                User.apartment_id == item.apartment_id,
                func.lower(User.role) == "resident",
            ).limit(1)
        )

        if assigned is not None:
            raise ValueError(
                "Apartment still has a resident assignment."
            )

        reserved = db.scalar(
            select(Lease.id).where(
                Lease.apartment_id == item.apartment_id,
                func.lower(Lease.status).in_(
                    [
                        "active",
                        "pending",
                        "scheduled",
                        "renewal_pending",
                    ]
                ),
                Lease.end_date >= today,
            ).limit(1)
        )

        if reserved is not None:
            raise ValueError(
                "Apartment has an active or reserved lease."
            )

        result = db.execute(
            update(MoveOutInspection)
            .where(
                MoveOutInspection.id == inspection_id,
                MoveOutInspection.status == "inspected",
            )
            .values(
                status="approved",
                approved_by=admin_user_id,
                approved_at=utc_now(),
            )
        )

        if result.rowcount != 1:
            raise ValueError(
                "Inspection changed during approval. "
                "Refresh and retry."
            )


# ==========================================================
# INSPECTION HISTORY
# ==========================================================

def get_inspection_history(
    admin_user_id: int,
    limit: int = 100,
) -> list[dict]:

    with get_db_session() as db:
        _require_admin(db, admin_user_id, permission="inspections.read")

        rows = db.execute(
            select(MoveOutInspection, Apartment, User)
            .join(
                Apartment,
                MoveOutInspection.apartment_id == Apartment.id,
            )
            .join(
                User,
                MoveOutInspection.resident_id == User.id,
            )
            .order_by(
                MoveOutInspection.created_at.desc(),
                MoveOutInspection.id.desc(),
            )
            .limit(max(1, min(limit, 500)))
        ).all()

        return [
            {
                "id": item.id,
                "unit": apartment.unit_number,
                "resident": resident.full_name,
                "source": item.source,
                "status": item.status,
                "inspection_date": item.inspection_date,
                "cleanliness": item.cleanliness,
                "walls_floors": item.walls_floors,
                "appliances": item.appliances,
                "estimated_repair_cost": float(
                    item.estimated_repair_cost or 0
                ),
                "inspected_by": item.inspected_by,
                "approved_by": item.approved_by,
                "approved_at": item.approved_at,
            }
            for item, apartment, resident in rows
        ]
