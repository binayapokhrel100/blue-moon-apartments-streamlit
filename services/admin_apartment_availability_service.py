
"""
Blue Moon Apartments
Apartment Availability Dashboard Service

Read-only availability calculations based on:
- Apartment occupancy
- Resident assignments
- Lease reservations
- Open move-out inspection holds

This service does not modify database records.
"""

from collections import Counter
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from database.db import get_db_session

from database.models import (
    Apartment,
    Lease,
    MoveOutInspection,
    User,
)

from services.admin_management_service import (
    _require_admin,
)


# ==========================================================
# AVAILABILITY STATUS DEFINITIONS
# ==========================================================

OCCUPIED = "Occupied"

AVAILABLE = "Vacant — Available"

INSPECTION_PENDING = "Vacant — Inspection Pending"

REPAIRS_REQUIRED = "Vacant — Repairs Required"

AWAITING_APPROVAL = "Vacant — Awaiting Approval"

RESERVED = "Vacant — Reserved"

NEEDS_REVIEW = "Needs Review"


STATUS_ORDER = (
    AVAILABLE,
    OCCUPIED,
    INSPECTION_PENDING,
    REPAIRS_REQUIRED,
    AWAITING_APPROVAL,
    RESERVED,
    NEEDS_REVIEW,
)


RESERVING_LEASE_STATUSES = (
    "active",
    "pending",
    "scheduled",
    "renewal_pending",
)


# ==========================================================
# GET ALL APARTMENT AVAILABILITY RECORDS
# ==========================================================

def get_apartment_availability(
    admin_id: int,
) -> list[dict]:
    """
    Compute availability for every apartment.

    Apartments are marked available only when
    there are no occupancy flags, resident
    assignments, lease reservations or open
    inspection holds.

    Requires an active administrator account.
    """

    today = date.today()

    with get_db_session() as db:

        _require_admin(
            db,
            admin_id,
        )

        # --------------------------------------
        # LOAD APARTMENTS
        # --------------------------------------

        apartments = db.scalars(
            select(Apartment).order_by(
                Apartment.unit_number
            )
        ).all()

        # --------------------------------------
        # LOAD RESIDENT ASSIGNMENTS
        # --------------------------------------

        assigned_residents = db.scalars(
            select(User).where(
                User.apartment_id.is_not(None),
                func.lower(User.role) == "resident",
            )
        ).all()

        # --------------------------------------
        # LOAD ACTIVE OR FUTURE LEASES
        # --------------------------------------

        blocking_leases = db.scalars(
            select(Lease).where(
                func.lower(Lease.status).in_(
                    RESERVING_LEASE_STATUSES
                ),
                Lease.end_date >= today,
            )
        ).all()

        # --------------------------------------
        # LOAD UNFINISHED INSPECTIONS
        # --------------------------------------

        open_inspections = db.scalars(
            select(MoveOutInspection).where(
                MoveOutInspection.status.in_(
                    ("pending", "inspected")
                )
            )
        ).all()

        # --------------------------------------
        # ORGANIZE RESIDENTS BY APARTMENT
        # --------------------------------------

        people_by_unit = {}

        for person in assigned_residents:
            people_by_unit.setdefault(
                person.apartment_id,
                [],
            ).append(person)

        # --------------------------------------
        # ORGANIZE LEASES BY APARTMENT
        # --------------------------------------

        leases_by_unit = {}

        for lease in blocking_leases:
            leases_by_unit.setdefault(
                lease.apartment_id,
                [],
            ).append(lease)

        # --------------------------------------
        # ORGANIZE INSPECTIONS BY APARTMENT
        # --------------------------------------

        inspections_by_unit = {}

        for inspection in open_inspections:

            inspections_by_unit.setdefault(
                inspection.apartment_id,
                [],
            ).append(inspection)

        # ==================================================
        # CLASSIFY EACH APARTMENT
        # ==================================================

        rows = []

        for apartment in apartments:

            assigned = people_by_unit.get(
                apartment.id,
                [],
            )

            active_assigned = [
                person
                for person in assigned
                if person.is_active
            ]

            inactive_assigned = [
                person
                for person in assigned
                if not person.is_active
            ]

            leases = leases_by_unit.get(
                apartment.id,
                [],
            )

            inspections = inspections_by_unit.get(
                apartment.id,
                [],
            )

            inspection = (
                inspections[0]
                if len(inspections) == 1
                else None
            )

            # ----------------------------------
            # FIND CURRENT LEASE CONFLICTS
            # ----------------------------------

            current_leases = [
                lease
                for lease in leases
                if (
                    str(lease.status).lower() == "active"
                    and lease.start_date <= today
                    and lease.end_date >= today
                )
            ]

            active_ids = {
                person.id
                for person in active_assigned
            }

            mismatched_leases = [
                lease
                for lease in current_leases
                if lease.resident_id not in active_ids
            ]

            # ==================================================
            # STATUS 1 — DATA NEEDS REVIEW
            # ==================================================

            if (
                len(inspections) > 1
                or inactive_assigned
                or (
                    apartment.is_occupied
                    and not active_assigned
                )
                or (
                    active_assigned
                    and not apartment.is_occupied
                )
                or len(active_assigned) > 1
                or mismatched_leases
                or (
                    active_assigned
                    and inspection is not None
                )
            ):

                status = NEEDS_REVIEW

                detail = (
                    "Assignment, occupancy, lease or "
                    "inspection data conflict. Review "
                    "records before taking action."
                )

            # ==================================================
            # STATUS 2 — OCCUPIED
            # ==================================================

            elif active_assigned:

                status = OCCUPIED

                detail = (
                    "Currently assigned to an "
                    "active resident."
                )

            # ==================================================
            # STATUS 3 — INSPECTION HOLDS
            # ==================================================

            elif inspection is not None:

                if inspection.status == "pending":

                    status = INSPECTION_PENDING

                    detail = (
                        "Complete the move-out inspection."
                    )

                else:

                    conditions = (
                        inspection.cleanliness,
                        inspection.walls_floors,
                        inspection.appliances,
                    )

                    if (
                        "Needs Repair" in conditions
                        and not inspection.repairs_completed
                    ):

                        status = REPAIRS_REQUIRED

                        detail = (
                            "Complete and document "
                            "required repairs."
                        )

                    else:

                        status = AWAITING_APPROVAL

                        detail = (
                            "Secure apartment access "
                            "before approval."
                            if not inspection.access_secured
                            else
                            "Inspection recorded; approve "
                            "release of the unit."
                        )

            # ==================================================
            # STATUS 4 — RESERVED
            # ==================================================

            elif leases:

                status = RESERVED

                detail = (
                    "An active or future lease blocks "
                    "new assignments."
                )

            # ==================================================
            # STATUS 5 — VACANT AND AVAILABLE
            # ==================================================

            else:

                status = AVAILABLE

                detail = (
                    "Vacant and available for a "
                    "new assignment."
                )

            # ----------------------------------
            # BUILD DASHBOARD ROW
            # ----------------------------------

            rows.append(
                {
                    "apartment_id": apartment.id,
                    "unit": apartment.unit_number,
                    "floor": apartment.floor,
                    "bedrooms": apartment.bedrooms,
                    "bathrooms": float(
                        apartment.bathrooms or 0
                    ),
                    "listed_rent": Decimal(
                        str(apartment.monthly_rent)
                    ),
                    "is_occupied": bool(
                        apartment.is_occupied
                    ),
                    "status": status,
                    "detail": detail,
                    "assigned_residents": (
                        ", ".join(
                            person.full_name
                            for person in active_assigned
                        )
                        or "—"
                    ),
                    "inspection_id": (
                        inspection.id
                        if inspection
                        else None
                    ),
                    "inspection_status": (
                        inspection.status
                        if inspection
                        else None
                    ),
                    "estimated_repairs": (
                        Decimal(
                            str(
                                inspection.estimated_repair_cost
                                or 0
                            )
                        )
                        if inspection
                        else Decimal("0.00")
                    ),
                    "lease_reservations": len(
                        leases
                    ),
                    "ready_for_assignment": (
                        status == AVAILABLE
                    ),
                }
            )

        return rows


# ==========================================================
# AVAILABILITY SUMMARY COUNTS
# ==========================================================

def get_availability_counts(
    admin_id: int,
) -> dict[str, int]:
    """
    Get counts by availability status.

    Uses the same classification rules as
    the apartment availability dashboard.
    """

    rows = get_apartment_availability(
        admin_id
    )

    counts = Counter(
        item["status"]
        for item in rows
    )

    return {
        status: counts[status]
        for status in STATUS_ORDER
    }
