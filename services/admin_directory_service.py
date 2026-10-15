
"""Blue Moon Apartments — RBAC-protected resident and apartment directory."""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from database.db import get_db_session
from database.models import Apartment, Lease, User
from services.admin_management_service import _require_admin


def get_admin_directory(
    admin_user_id: int,
    *,
    include_residents: bool = True,
    include_apartments: bool = True,
) -> dict:
    """
    Return authorized directory data.

    The default requires both tenants.read and apartments.read.

    For apartment-only access, use:
        get_admin_directory(admin_id, include_residents=False)

    Apartment-only results omit resident names.
    """

    with get_db_session() as db:

        # Verify identity and active employee status.
        _require_admin(db, admin_user_id)

        if include_residents:
            _require_admin(
                db,
                admin_user_id,
                permission="tenants.read",
            )

        if include_apartments:
            _require_admin(
                db,
                admin_user_id,
                permission="apartments.read",
            )

        # ==========================================
        # RESIDENT DIRECTORY
        # ==========================================

        residents = []

        if include_residents:

            resident_records = db.scalars(
                select(User)
                .options(joinedload(User.apartment))
                .where(func.lower(User.role) == "resident")
                .order_by(
                    User.last_name,
                    User.first_name,
                    User.id,
                )
            ).all()

            leased_resident_ids = set(
                db.scalars(
                    select(Lease.resident_id).where(
                        func.lower(Lease.status) == "active",
                        Lease.end_date >= date.today(),
                    )
                ).all()
            )

            residents = [
                {
                    "id": resident.id,
                    "name": resident.full_name,
                    "first_name": resident.first_name,
                    "last_name": resident.last_name,
                    "email": resident.email,
                    "phone": resident.phone or "",
                    "apartment_id": resident.apartment_id,
                    "unit": (
                        resident.apartment.unit_number
                        if resident.apartment
                        else "Unassigned"
                    ),
                    "is_active": bool(resident.is_active),
                    "has_active_lease": (
                        resident.id in leased_resident_ids
                    ),
                    "joined": (
                        resident.created_at.strftime("%b %d, %Y")
                        if resident.created_at
                        else "—"
                    ),
                }
                for resident in resident_records
            ]

        # ==========================================
        # APARTMENT DIRECTORY
        # ==========================================

        apartments = []

        if include_apartments:

            apartment_records = db.scalars(
                select(Apartment)
                .options(joinedload(Apartment.residents))
                .order_by(Apartment.unit_number)
            ).unique().all()

            for unit in apartment_records:

                active_members = [
                    member
                    for member in unit.residents
                    if member.is_active
                    and str(member.role or "").strip().lower()
                    == "resident"
                ]

                resident_count = len(active_members)

                # Do not expose resident names to an
                # apartment-only caller without tenants.read.
                if include_residents:
                    resident_names = (
                        ", ".join(
                            member.full_name
                            for member in active_members
                        ) or "—"
                    )
                else:
                    resident_names = (
                        "Restricted"
                        if resident_count
                        else "—"
                    )

                apartments.append(
                    {
                        "id": unit.id,
                        "unit": unit.unit_number,
                        "floor": unit.floor,
                        "bedrooms": unit.bedrooms,
                        "bathrooms": str(unit.bathrooms),
                        "monthly_rent": (
                            f"${unit.monthly_rent:,.2f}"
                        ),
                        "rent_value": float(unit.monthly_rent),
                        "is_occupied": bool(unit.is_occupied),
                        "resident_count": resident_count,
                        "resident_names": resident_names,
                    }
                )

        return {
            "residents": residents,
            "apartments": apartments,
        }
