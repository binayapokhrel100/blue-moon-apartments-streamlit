import os
from datetime import date, datetime
from decimal import Decimal

from dotenv import load_dotenv
from sqlalchemy import select

from core.security import hash_password
from database.db import (
    get_db_session,
    init_db,
)
from database.models import (
    Apartment,
    Lease,
    Notification,
    Payment,
    User,
)

from database.models import (
    Apartment,
    Lease,
    MaintenanceRequest,
    MaintenanceUpdate,
    Notification,
    Payment,
    User,
)


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

        # ============================================
        # APARTMENT
        # ============================================

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

        # ============================================
        # USER
        # ============================================

        user = db.scalar(
            select(User).where(
                User.email
                == DEMO_EMAIL.lower()
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

        # ============================================
        # LEASE
        # ============================================

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
                start_date=date(
                    2026,
                    6,
                    1,
                ),
                end_date=date(
                    2027,
                    5,
                    31,
                ),
                monthly_rent=Decimal(
                    "1250.00"
                ),
                security_deposit=Decimal(
                    "1250.00"
                ),
                status="active",
            )

            db.add(lease)
            db.flush()


        # ============================================
        # MAINTENANCE REQUEST
        # ============================================

        maintenance_request = db.scalar(
            select(
                MaintenanceRequest
            ).where(
                MaintenanceRequest.request_number
                == "MR-2026-0142"
            )
        )

        if maintenance_request is None:

            maintenance_request = (
                MaintenanceRequest(
                    request_number=(
                        "MR-2026-0142"
                    ),
                    resident_id=user.id,
                    apartment_id=apartment.id,
                    category="Plumbing",
                    location_detail=(
                        "Kitchen sink"
                    ),
                    description=(
                        "The kitchen faucet is "
                        "leaking continuously "
                        "under the handle."
                    ),
                    urgency="Medium",
                    status="In Progress",
                    technician_name=(
                        "Carlos Rivera"
                    ),
                    scheduled_start=datetime(
                        2026,
                        9,
                        8,
                        10,
                        0,
                    ),
                    scheduled_end=datetime(
                        2026,
                        9,
                        8,
                        12,
                        0,
                    ),
                    created_at=datetime(
                        2026,
                        9,
                        5,
                        9,
                        30,
                    ),
                    updated_at=datetime(
                        2026,
                        9,
                        8,
                        10,
                        15,
                    ),
                )
            )

            db.add(
                maintenance_request
            )

            db.flush()

        # ============================================
        # MAINTENANCE TIMELINE
        # ============================================

        maintenance_updates = [
            {
                "status": "Submitted",
                "message": (
                    "Maintenance request "
                    "submitted by resident."
                ),
                "created_at": datetime(
                    2026,
                    9,
                    5,
                    9,
                    30,
                ),
            },
            {
                "status": "Scheduled",
                "message": (
                    "Your maintenance request "
                    "has been scheduled for "
                    "September 8th between "
                    "10 AM – 12 PM."
                ),
                "created_at": datetime(
                    2026,
                    9,
                    6,
                    14,
                    0,
                ),
            },
            {
                "status": "In Progress",
                "message": (
                    "Technician Carlos Rivera "
                    "arrived at your unit. "
                    "The request is now "
                    "In Progress."
                ),
                "created_at": datetime(
                    2026,
                    9,
                    8,
                    10,
                    15,
                ),
            },
        ]

        for item in maintenance_updates:

            existing_update = db.scalar(
                select(
                    MaintenanceUpdate
                ).where(
                    MaintenanceUpdate.request_id
                    == maintenance_request.id,

                    MaintenanceUpdate.status
                    == item["status"],

                    MaintenanceUpdate.created_at
                    == item["created_at"],
                )
            )

            if existing_update is None:

                db.add(
                    MaintenanceUpdate(
                        request_id=(
                            maintenance_request.id
                        ),
                        **item,
                    )
                )  

        # ============================================
        # SEPTEMBER PAYMENT
        # ============================================

        confirmation = (
            "BMP-20260901-7842"
        )

        payment = db.scalar(
            select(Payment).where(
                Payment.confirmation_number
                == confirmation
            )
        )

        if payment is None:

            payment = Payment(
                resident_id=user.id,
                lease_id=lease.id,
                amount=Decimal(
                    "1250.00"
                ),
                payment_month=date(
                    2026,
                    9,
                    1,
                ),
                payment_method=(
                    "Bank Account •••• 4821"
                ),
                status="confirmed",
                confirmation_number=(
                    confirmation
                ),
                paid_at=datetime(
                    2026,
                    9,
                    1,
                    8,
                    2,
                ),
            )

            db.add(payment)

        # ============================================
        # NOTIFICATIONS
        # ============================================

        notifications = [
            {
                "title": (
                    "Payment Confirmed"
                ),
                "message": (
                    "Your rent payment of "
                    "$1,250.00 for September "
                    "was received. "
                    "Confirmation: "
                    "BMP-20260901-7842"
                ),
                "notification_type": (
                    "payment"
                ),
                "is_read": False,
                "is_alert": False,
                "created_at": datetime(
                    2026,
                    9,
                    1,
                    8,
                    2,
                ),
            },
            {
                "title": (
                    "Maintenance Update — "
                    "MR-2026-0142"
                ),
                "message": (
                    "Your maintenance request "
                    "(Leaking faucet) is now "
                    "In Progress. Technician "
                    "Carlos Rivera arrived "
                    "at your unit."
                ),
                "notification_type": (
                    "maintenance"
                ),
                "is_read": False,
                "is_alert": False,
                "created_at": datetime(
                    2026,
                    9,
                    8,
                    10,
                    15,
                ),
            },
            {
                "title": (
                    "New Announcement: "
                    "Pool Maintenance"
                ),
                "message": (
                    "The community pool will "
                    "be closed for maintenance "
                    "on October 5th from "
                    "8 AM to 4 PM."
                ),
                "notification_type": (
                    "announcement"
                ),
                "is_read": False,
                "is_alert": False,
                "created_at": datetime(
                    2026,
                    9,
                    10,
                    9,
                    0,
                ),
            },
            {
                "title": (
                    "New Login Detected"
                ),
                "message": (
                    "A new login to your "
                    "account was detected on "
                    "Sep 10, 2026 at 8:45 AM "
                    "from iPhone — Safari. "
                    "If this was not you, "
                    "please change your "
                    "password immediately."
                ),
                "notification_type": (
                    "security"
                ),
                "is_read": True,
                "is_alert": True,
                "created_at": datetime(
                    2026,
                    9,
                    10,
                    8,
                    45,
                ),
            },
            {
                "title": (
                    "Maintenance Scheduled — "
                    "MR-2026-0142"
                ),
                "message": (
                    "Your maintenance request "
                    "has been scheduled for "
                    "September 8th between "
                    "10 AM – 12 PM."
                ),
                "notification_type": (
                    "maintenance"
                ),
                "is_read": True,
                "is_alert": False,
                "created_at": datetime(
                    2026,
                    9,
                    6,
                    14,
                    0,
                ),
            },
            {
                "title": (
                    "Password Changed"
                ),
                "message": (
                    "Your account password "
                    "was successfully changed "
                    "on Aug 20, 2026. "
                    "If you did not make this "
                    "change, contact us "
                    "immediately."
                ),
                "notification_type": (
                    "security"
                ),
                "is_read": True,
                "is_alert": True,
                "created_at": datetime(
                    2026,
                    8,
                    20,
                    15,
                    12,
                ),
            },
            {
                "title": (
                    "New Community News"
                ),
                "message": (
                    "A bike share station "
                    "has been added right "
                    "outside Blue Moon "
                    "Apartments!"
                ),
                "notification_type": (
                    "community"
                ),
                "is_read": True,
                "is_alert": False,
                "created_at": datetime(
                    2026,
                    9,
                    4,
                    11,
                    0,
                ),
            },
        ]

        for item in notifications:

            existing = db.scalar(
                select(Notification).where(
                    Notification.user_id
                    == user.id,
                    Notification.title
                    == item["title"],
                    Notification.created_at
                    == item["created_at"],
                )
            )

            if existing is None:

                db.add(
                    Notification(
                        user_id=user.id,
                        **item,
                    )
                )

    print(
        "Blue Moon database seeded successfully."
    )

    print(
        f"Demo resident: {DEMO_EMAIL}"
    )


if __name__ == "__main__":
    seed_database()