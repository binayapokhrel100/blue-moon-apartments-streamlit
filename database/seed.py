import os
from datetime import date
from decimal import Decimal

from dotenv import load_dotenv
from sqlalchemy import select

from core.security import hash_password
from database.db import get_db_session, init_db
from database.models import Apartment, Lease, User


load_dotenv()


DEMO_EMAIL = os.getenv(
    "DEMO_USER_EMAIL",
    "sarah.mitchell@bluemoon.demo",
)

DEMO_PASSWORD = os.getenv(
    "DEMO_USER_PASSWORD",
    "BlueMoon123!",
)


def seed_database() -> None:

    init_db()

    with get_db_session() as db:

        apartment = db.scalar(
            select(Apartment).where(
                Apartment.unit_number == "4B"
            )
        )

        if apartment is None:

            apartment = Apartment(
                unit_number="4B",
                floor=4,
                bedrooms=2,
                bathrooms=Decimal("2.0"),
                monthly_rent=Decimal("1250.00"),
                is_occupied=True,
            )

            db.add(apartment)
            db.flush()

        user = db.scalar(
            select(User).where(
                User.email == DEMO_EMAIL.lower()
            )
        )

        if user is None:

            user = User(
                first_name="Sarah",
                last_name="Mitchell",
                email=DEMO_EMAIL.lower(),
                password_hash=hash_password(
                    DEMO_PASSWORD
                ),
                phone="(214) 555-0188",
                role="resident",
                apartment_id=apartment.id,
                is_active=True,
            )

            db.add(user)
            db.flush()

        lease = db.scalar(
            select(Lease).where(
                Lease.resident_id == user.id,
                Lease.status == "active",
            )
        )

        if lease is None:

            lease = Lease(
                resident_id=user.id,
                apartment_id=apartment.id,
                start_date=date(2026, 6, 1),
                end_date=date(2027, 5, 31),
                monthly_rent=Decimal("1250.00"),
                security_deposit=Decimal("1250.00"),
                status="active",
            )

            db.add(lease)

    print("Blue Moon database seeded successfully.")
    print(f"Demo resident: {DEMO_EMAIL}")


if __name__ == "__main__":
    seed_database()