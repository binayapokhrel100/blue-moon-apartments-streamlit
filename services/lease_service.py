from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from database.db import get_db_session
from database.models import Lease


def calculate_lease_progress(
    start_date: date,
    end_date: date,
    as_of: date | None = None,
) -> int:

    if end_date <= start_date:
        raise ValueError(
            "Lease end date must be "
            "after the start date."
        )

    if as_of is None:
        as_of = date.today()

    if as_of <= start_date:
        return 0

    if as_of >= end_date:
        return 100

    total_days = (
        end_date - start_date
    ).days

    elapsed_days = (
        as_of - start_date
    ).days

    percentage = round(
        (
            elapsed_days
            / total_days
        )
        * 100
    )

    return max(
        0,
        min(
            100,
            percentage,
        ),
    )


def calculate_days_remaining(
    end_date: date,
    as_of: date | None = None,
) -> int:

    if as_of is None:
        as_of = date.today()

    return max(
        0,
        (
            end_date
            - as_of
        ).days,
    )


def get_current_lease(
    user_id: int,
) -> dict | None:

    with get_db_session() as db:

        statement = (
            select(Lease)
            .options(
                joinedload(
                    Lease.apartment
                )
            )
            .where(
                Lease.resident_id
                == user_id,
                Lease.status
                == "active",
            )
            .order_by(
                Lease.end_date.desc()
            )
        )

        lease = db.scalar(
            statement
        )

        if lease is None:
            return None

        return _lease_to_dict(
            lease
        )


def get_lease_history(
    user_id: int,
) -> list[dict]:

    with get_db_session() as db:

        statement = (
            select(Lease)
            .options(
                joinedload(
                    Lease.apartment
                )
            )
            .where(
                Lease.resident_id
                == user_id
            )
            .order_by(
                Lease.start_date.desc()
            )
        )

        leases = db.scalars(
            statement
        ).all()

        return [
            _lease_to_dict(lease)
            for lease in leases
        ]


def _lease_to_dict(
    lease: Lease,
) -> dict:

    apartment = lease.apartment

    return {
        "id": lease.id,
        "resident_id": (
            lease.resident_id
        ),
        "apartment_id": (
            lease.apartment_id
        ),
        "unit_number": (
            apartment.unit_number
            if apartment
            else None
        ),
        "bedrooms": (
            apartment.bedrooms
            if apartment
            else None
        ),
        "bathrooms": (
            Decimal(
                apartment.bathrooms
            )
            if apartment
            else None
        ),
        "start_date": (
            lease.start_date
        ),
        "end_date": (
            lease.end_date
        ),
        "monthly_rent": Decimal(
            lease.monthly_rent
        ),
        "security_deposit": Decimal(
            lease.security_deposit
        ),
        "status": lease.status,
        "progress": (
            calculate_lease_progress(
                lease.start_date,
                lease.end_date,
            )
        ),
        "days_remaining": (
            calculate_days_remaining(
                lease.end_date
            )
        ),
    }