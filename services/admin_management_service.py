
"""Blue Moon Apartments — authorized tenant and apartment management."""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select, update
from core.admin_permissions import (
    ALL_PERMISSIONS,
    permissions_for,
)

from core.security import hash_password
from database.db import get_db_session
from database.models import (
    AdminEmployee,
    Apartment,
    Lease,
    MoveOutInspection,
    User,
    AdminRoleAssignment,
)


EMAIL_PATTERN = re.compile(
    r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
)


# ==========================================================
# ADMINISTRATOR AUTHORIZATION WITH RBAC
# ==========================================================

def _require_admin(
    db,
    admin_user_id: int,
    permission: str | None = None,
) -> None:
    """
    Verify administrator identity and employment status.

    When a permission is specified, verify it against
    the administrator's current database role.

    Services not yet migrated may still call this
    function without a permission. Those call sites
    must be migrated before RBAC is fully enforced.
    """

    # --------------------------------------------------
    # VERIFY ACTIVE ADMINISTRATOR
    # --------------------------------------------------

    admin = db.scalar(
        select(User).where(
            User.id == admin_user_id,
            func.lower(User.role) == "admin",
            User.is_active.is_(True),
        )
    )

    if admin is None:
        raise PermissionError(
            "Administrator access required."
        )

    # --------------------------------------------------
    # VERIFY ACTIVE EMPLOYEE RECORD
    # --------------------------------------------------

    employee = db.scalar(
        select(AdminEmployee.id).where(
            AdminEmployee.user_id == admin.id,
            AdminEmployee.is_active.is_(True),
        )
    )

    if employee is None:
        raise PermissionError(
            "Administrator employee record "
            "is inactive or missing."
        )

    # --------------------------------------------------
    # PERMISSIONLESS CALLS ARE LEGACY CALL SITES
    # --------------------------------------------------

    if permission is None:
        return

    # --------------------------------------------------
    # VALIDATE PERMISSION NAME
    # --------------------------------------------------

    if permission not in ALL_PERMISSIONS:
        raise ValueError(
            f"Unknown administrator permission: {permission}"
        )

    # --------------------------------------------------
    # LOOK UP CURRENT ROLE FROM DATABASE
    # --------------------------------------------------

    assigned_role = db.scalar(
        select(AdminRoleAssignment.role).where(
            AdminRoleAssignment.user_id == admin.id
        )
    )

    # --------------------------------------------------
    # ENFORCE REQUIRED PERMISSION
    # --------------------------------------------------

    allowed = permissions_for(assigned_role)

    if permission not in allowed:
        raise PermissionError(
            "You do not have permission to perform "
            f"this operation: {permission}"
        )


# ==========================================================
# RESIDENT VALIDATION
# ==========================================================

def _clean_resident(
    first_name: str,
    last_name: str,
    email: str,
    phone: str,
):

    first = (first_name or "").strip()
    last = (last_name or "").strip()
    mail = (email or "").strip().lower()
    telephone = (phone or "").strip()

    if (
        not first
        or not last
        or len(first) > 100
        or len(last) > 100
    ):
        raise ValueError(
            "First and last names are required "
            "(maximum 100 characters each)."
        )

    if (
        len(mail) > 255
        or not EMAIL_PATTERN.fullmatch(mail)
    ):
        raise ValueError(
            "Enter a valid email address."
        )

    if len(telephone) > 30:
        raise ValueError(
            "Phone number must be "
            "30 characters or fewer."
        )

    return first, last, mail, telephone or None


def _check_unique_email(
    db,
    email: str,
    ignore_id: int | None = None,
) -> None:

    query = select(User.id).where(
        func.lower(User.email) == email
    )

    if ignore_id is not None:
        query = query.where(
            User.id != ignore_id
        )

    if db.scalar(query) is not None:
        raise ValueError(
            "That email address is already registered."
        )


# ==========================================================
# APARTMENT LOOKUP
# ==========================================================

def _get_apartment(
    db,
    apartment_id: int | None,
) -> Apartment | None:

    if apartment_id is None:
        return None

    apartment = db.get(
        Apartment,
        apartment_id,
    )

    if apartment is None:
        raise ValueError(
            "The selected apartment no longer exists."
        )

    return apartment


# ==========================================================
# ACTIVE LEASE LOOKUP
# ==========================================================

def _active_leases(
    db,
    resident_id: int,
) -> list[Lease]:

    return list(
        db.scalars(
            select(Lease).where(
                Lease.resident_id == resident_id,
                func.lower(Lease.status) == "active",
                Lease.end_date >= date.today(),
            )
        ).all()
    )


# ==========================================================
# VACANT APARTMENT VALIDATION AND RESERVATION
# ==========================================================

def _claim_vacant_apartment(
    db,
    apartment_id: int,
    exclude_resident_id: int | None = None,
) -> Apartment:
    """
    Verify and reserve a vacant apartment.

    Prevent duplicate assignments caused by:
    - An occupied apartment flag.
    - Another assigned resident, active or inactive.
    - An existing unexpired active lease.
    - Another transaction claiming the apartment first.

    The reservation is part of the caller's transaction.
    """

    apartment = _get_apartment(
        db,
        apartment_id,
    )

    # ------------------------------------------
    # CHECK RECORDED OCCUPANCY
    # ------------------------------------------

    if apartment.is_occupied:
        raise ValueError(
            f"Apartment {apartment.unit_number} is "
            "already occupied. Choose a vacant apartment."
        )

    # ------------------------------------------
    # BLOCK APARTMENTS AWAITING INSPECTION
    # ------------------------------------------

    inspection_hold = db.scalar(
        select(MoveOutInspection.id).where(
            MoveOutInspection.apartment_id == apartment_id,
            MoveOutInspection.status.in_(
                ["pending", "inspected"]
            ),
        ).limit(1)
    )

    if inspection_hold is not None:
        raise ValueError(
            f"Apartment {apartment.unit_number} is "
            "under an inspection hold. "
            "Complete and approve its move-out "
            "inspection before assigning a resident."
        )

    # ------------------------------------------
    # CHECK RESIDENT ASSIGNMENTS
    # ------------------------------------------

    assigned_query = select(User.id).where(
        User.apartment_id == apartment_id,
        func.lower(User.role) == "resident",
    )

    if exclude_resident_id is not None:
        assigned_query = assigned_query.where(
            User.id != exclude_resident_id
        )

    existing_resident = db.scalar(
        assigned_query.limit(1)
    )

    if existing_resident is not None:
        raise ValueError(
            f"Apartment {apartment.unit_number} is "
            "already assigned to another resident. "
            "Resolve the existing assignment first."
        )

    # ------------------------------------------
    # CHECK ACTIVE LEASES
    # ------------------------------------------

    active_lease = db.scalar(
        select(Lease.id).where(
            Lease.apartment_id == apartment_id,
            func.lower(Lease.status) == "active",
            Lease.end_date >= date.today(),
        ).limit(1)
    )

    if active_lease is not None:
        raise ValueError(
            f"Apartment {apartment.unit_number} "
            "has an existing active lease. "
            "Resolve the lease first."
        )

    # ------------------------------------------
    # RESERVE APARTMENT AT DATABASE LEVEL
    # ------------------------------------------

    result = db.execute(
        update(Apartment)
        .where(
            Apartment.id == apartment_id,
            Apartment.is_occupied.is_(False),
        )
        .values(
            is_occupied=True
        )
    )

    if result.rowcount != 1:
        raise ValueError(
            "This apartment was just occupied "
            "or updated by another administrator. "
            "Refresh and choose another unit."
        )

    db.flush()

    return apartment


# ==========================================================
# RECALCULATE OCCUPANCY
# ==========================================================

def _sync_occupancy(
    db,
    apartment_ids: set[int | None],
) -> None:
    """Update occupancy after resident or lease changes."""

    db.flush()

    for apartment_id in apartment_ids:

        if apartment_id is None:
            continue

        apartment = db.get(
            Apartment,
            apartment_id,
        )

        if apartment is None:
            continue

        active_residents = db.scalar(
            select(func.count(User.id)).where(
                User.apartment_id == apartment_id,
                func.lower(User.role) == "resident",
                User.is_active.is_(True),
            )
        ) or 0

        active_leases = db.scalar(
            select(func.count(Lease.id)).where(
                Lease.apartment_id == apartment_id,
                func.lower(Lease.status) == "active",
                Lease.end_date >= date.today(),
            )
        ) or 0

        apartment.is_occupied = bool(
            active_residents or active_leases
        )


# ==========================================================
# LEASE VALIDATION
# ==========================================================

def _validate_lease_dates(
    start: date,
    end: date,
) -> None:

    if (
        not isinstance(start, date)
        or isinstance(start, datetime)
    ):
        raise ValueError(
            "Choose a valid lease start date."
        )

    if (
        not isinstance(end, date)
        or isinstance(end, datetime)
    ):
        raise ValueError(
            "Choose a valid lease end date."
        )

    if end <= start:
        raise ValueError(
            "Lease end date must be later "
            "than its start date."
        )

    if not start <= date.today() <= end:
        raise ValueError(
            "An active lease must include today's date. "
            "Future move-ins require a separate "
            "pending-lease workflow."
        )


def _validate_deposit(
    value: object,
) -> Decimal:

    try:
        deposit = Decimal(
            str(value)
        )
    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ):
        raise ValueError(
            "Enter a valid security deposit."
        ) from None

    if (
        not deposit.is_finite()
        or not Decimal("0")
        <= deposit
        <= Decimal("99999999.99")
    ):
        raise ValueError(
            "Security deposit must be between "
            "$0 and $99,999,999.99."
        )

    if deposit != deposit.quantize(
        Decimal("0.01")
    ):
        raise ValueError(
            "Security deposit must have no more "
            "than two decimal places."
        )

    return deposit


# ==========================================================
# CREATE RESIDENT WITH ACTIVE LEASE
# ==========================================================

def create_resident(
    admin_user_id: int,
    *,
    first_name: str,
    last_name: str,
    email: str,
    password: str,
    apartment_id: int | None,
    lease_start: date,
    lease_end: date,
    security_deposit: object = 0,
    phone: str = "",
) -> int:

    first, last, mail, telephone = _clean_resident(
        first_name,
        last_name,
        email,
        phone,
    )

    password_length = len(
        (password or "").encode("utf-8")
    )

    if not 12 <= password_length <= 72:
        raise ValueError(
            "Password must contain 12–72 UTF-8 bytes."
        )

    if apartment_id is None:
        raise ValueError(
            "Apartment assignment is required "
            "when adding a resident."
        )

    _validate_lease_dates(
        lease_start,
        lease_end,
    )

    deposit = _validate_deposit(
        security_deposit
    )

    with get_db_session() as db:

        _require_admin(
            db,
            admin_user_id,
            permission="tenants.create"
        )

        _check_unique_email(
            db,
            mail,
        )

        # Reject occupied or already assigned units.
        # A conditional UPDATE reserves the unit.
        apartment = _claim_vacant_apartment(
            db,
            apartment_id,
        )

        # --------------------------------------
        # CREATE RESIDENT
        # --------------------------------------

        resident = User(
            first_name=first,
            last_name=last,
            email=mail,
            phone=telephone,
            password_hash=hash_password(password),
            role="resident",
            is_active=True,
            apartment_id=apartment_id,
        )

        db.add(resident)
        db.flush()

        # --------------------------------------
        # CREATE LEASE
        # --------------------------------------

        lease = Lease(
            resident_id=resident.id,
            apartment_id=apartment_id,
            start_date=lease_start,
            end_date=lease_end,
            monthly_rent=apartment.monthly_rent,
            security_deposit=deposit,
            status="active",
        )

        db.add(lease)
        db.flush()

        _sync_occupancy(
            db,
            {apartment_id},
        )

        return resident.id


# ==========================================================
# UPDATE RESIDENT
# ==========================================================

def update_resident(
    admin_user_id: int,
    resident_id: int,
    *,
    first_name: str,
    last_name: str,
    email: str,
    phone: str,
    apartment_id: int | None,
    is_active: bool,
) -> None:
    """
    Update resident details safely.

    A resident may keep their current unit.
    Moving to an occupied or assigned unit is forbidden.
    Active lease restrictions remain enforced.
    """

    first, last, mail, telephone = _clean_resident(
        first_name,
        last_name,
        email,
        phone,
    )

    with get_db_session() as db:

        _require_admin(
            db,
            admin_user_id,
            permission="tenants.update",
        )

        resident = db.get(
            User,
            resident_id,
        )

        if (
            resident is None
            or str(resident.role or "").lower()
            != "resident"
        ):
            raise ValueError(
                "Resident not found."
            )

        _get_apartment(
            db,
            apartment_id,
        )

        _check_unique_email(
            db,
            mail,
            ignore_id=resident_id,
        )

        previous_apartment = resident.apartment_id

        apartment_changed = (
            apartment_id != previous_apartment
        )

        # --------------------------------------
        # PROTECT EXISTING ACTIVE LEASE
        # --------------------------------------

        for lease in _active_leases(
            db,
            resident_id,
        ):

            if not is_active:
                raise ValueError(
                    "This resident has an active lease. "
                    "Resolve the lease before "
                    "deactivating the account."
                )

            if apartment_id != lease.apartment_id:
                raise ValueError(
                    "This resident has an active lease "
                    "for another unit. Update the lease "
                    "through a dedicated lease workflow first."
                )

        # --------------------------------------
        # PREVENT INVALID NEW ASSIGNMENT
        # --------------------------------------

        if (
            apartment_changed
            and apartment_id is not None
        ):

            if not is_active:
                raise ValueError(
                    "Activate the resident account before "
                    "assigning a new apartment."
                )

            # This rejects:
            # - Already occupied apartments
            # - Other residents' apartments
            # - Apartments with unexpired active leases
            # - Units claimed concurrently
            _claim_vacant_apartment(
                db,
                apartment_id,
                exclude_resident_id=resident_id,
            )

        # --------------------------------------
        # UPDATE RESIDENT FIELDS
        # --------------------------------------

        resident.first_name = first
        resident.last_name = last
        resident.email = mail
        resident.phone = telephone
        resident.apartment_id = apartment_id
        resident.is_active = bool(is_active)

        # --------------------------------------
        # SYNCHRONIZE OCCUPANCY
        # --------------------------------------

        _sync_occupancy(
            db,
            {
                previous_apartment,
                apartment_id,
            },
        )


# ==========================================================
# APARTMENT VALIDATION
# ==========================================================

def _clean_apartment(
    unit_number: str,
    floor: int | None,
    bedrooms: int,
    bathrooms: object,
    monthly_rent: object,
):

    unit = (
        unit_number or ""
    ).strip().upper()

    if not unit or len(unit) > 20:
        raise ValueError(
            "Unit number is required "
            "(maximum 20 characters)."
        )

    if (
        floor is not None
        and not -5 <= floor <= 200
    ):
        raise ValueError(
            "Floor must be between -5 and 200."
        )

    if not 0 <= bedrooms <= 20:
        raise ValueError(
            "Bedrooms must be between 0 and 20."
        )

    try:
        baths = Decimal(
            str(bathrooms)
        )

        rent = Decimal(
            str(monthly_rent)
        )

    except (
        InvalidOperation,
        ValueError,
        TypeError,
    ):
        raise ValueError(
            "Enter valid bathroom and rent amounts."
        ) from None

    if (
        not baths.is_finite()
        or not Decimal("0.5")
        <= baths
        <= Decimal("99.9")
    ):
        raise ValueError(
            "Bathrooms must be between 0.5 and 99.9."
        )

    if baths != baths.quantize(
        Decimal("0.1")
    ):
        raise ValueError(
            "Bathrooms must have at most "
            "one decimal place."
        )

    if (
        not rent.is_finite()
        or not Decimal("0.01")
        <= rent
        <= Decimal("99999999.99")
    ):
        raise ValueError(
            "Monthly rent must be between "
            "$0.01 and $99,999,999.99."
        )

    if rent != rent.quantize(
        Decimal("0.01")
    ):
        raise ValueError(
            "Monthly rent must have no more "
            "than two decimal places."
        )

    return unit, floor, bedrooms, baths, rent


def _check_unique_unit(
    db,
    unit: str,
    ignore_id: int | None = None,
) -> None:

    query = select(Apartment.id).where(
        func.upper(Apartment.unit_number) == unit
    )

    if ignore_id is not None:
        query = query.where(
            Apartment.id != ignore_id
        )

    if db.scalar(query) is not None:
        raise ValueError(
            "This apartment unit number "
            "already exists."
        )


# ==========================================================
# CREATE APARTMENT
# ==========================================================

def create_apartment(
    admin_user_id: int,
    *,
    unit_number: str,
    floor: int | None,
    bedrooms: int,
    bathrooms: object,
    monthly_rent: object,
) -> int:

    unit, floor, beds, baths, rent = (
        _clean_apartment(
            unit_number,
            floor,
            bedrooms,
            bathrooms,
            monthly_rent,
        )
    )

    with get_db_session() as db:

        _require_admin(
            db,
            admin_user_id,
            permission="apartments.create"
        )

        _check_unique_unit(
            db,
            unit,
        )

        apartment = Apartment(
            unit_number=unit,
            floor=floor,
            bedrooms=beds,
            bathrooms=baths,
            monthly_rent=rent,
            is_occupied=False,
        )

        db.add(apartment)
        db.flush()

        return apartment.id


# ==========================================================
# UPDATE APARTMENT
# ==========================================================

def update_apartment(
    admin_user_id: int,
    apartment_id: int,
    *,
    unit_number: str,
    floor: int | None,
    bedrooms: int,
    bathrooms: object,
    monthly_rent: object,
) -> None:

    unit, floor, beds, baths, rent = (
        _clean_apartment(
            unit_number,
            floor,
            bedrooms,
            bathrooms,
            monthly_rent,
        )
    )

    with get_db_session() as db:

        _require_admin(
            db,
            admin_user_id,
            permission="apartments.update",
        )

        apartment = db.get(
            Apartment,
            apartment_id,
        )

        if apartment is None:
            raise ValueError(
                "Apartment not found."
            )

        _check_unique_unit(
            db,
            unit,
            ignore_id=apartment_id,
        )

        apartment.unit_number = unit
        apartment.floor = floor
        apartment.bedrooms = beds
        apartment.bathrooms = baths
        apartment.monthly_rent = rent
