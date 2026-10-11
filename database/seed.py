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
    Announcement,
    Apartment,
    CommunityNews,
    Lease,
    MaintenanceRequest,
    MaintenanceUpdate,
    Notification,
    Payment,
    User,
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
        # ANNOUNCEMENTS
        # ============================================

        announcements = [
            {
                "title": (
                    "Fire Alarm Inspection"
                ),
                "message": (
                    "Annual fire alarm inspections "
                    "will take place on October 15 "
                    "between 9 AM and 3 PM. "
                    "Maintenance staff may need "
                    "brief access to each apartment."
                ),
                "category": "Safety",
                "priority": "Important",
                "published_at": datetime(
                    2026,
                    10,
                    10,
                    9,
                    0,
                ),
                "expires_at": datetime(
                    2026,
                    10,
                    16,
                    23,
                    59,
                ),
            },
            {
                "title": (
                    "Parking Lot Resurfacing"
                ),
                "message": (
                    "Sections of the resident parking "
                    "lot will be resurfaced from "
                    "October 18 through October 20. "
                    "Temporary parking instructions "
                    "will be posted in advance."
                ),
                "category": "Maintenance",
                "priority": "Important",
                "published_at": datetime(
                    2026,
                    10,
                    9,
                    14,
                    30,
                ),
                "expires_at": datetime(
                    2026,
                    10,
                    21,
                    23,
                    59,
                ),
            },
            {
                "title": (
                    "Resident Fall Social"
                ),
                "message": (
                    "Join your neighbors for the "
                    "Blue Moon Fall Social on "
                    "October 24 from 5 PM to 7 PM "
                    "in the community courtyard."
                ),
                "category": "Events",
                "priority": "Normal",
                "published_at": datetime(
                    2026,
                    10,
                    8,
                    11,
                    0,
                ),
                "expires_at": datetime(
                    2026,
                    10,
                    25,
                    0,
                    0,
                ),
            },
        ]

        for item in announcements:

            existing = db.scalar(
                select(
                    Announcement
                ).where(
                    Announcement.title
                    == item["title"]
                )
            )

            if existing is None:

                db.add(
                    Announcement(
                        message=item[
                            "message"
                        ],
                        title=item[
                            "title"
                        ],
                        category=item[
                            "category"
                        ],
                        priority=item[
                            "priority"
                        ],
                        is_published=True,
                        published_at=item[
                            "published_at"
                        ],
                        expires_at=item[
                            "expires_at"
                        ],
                    )
                )

        # ============================================
        # COMMUNITY NEWS
        # ============================================

        community_news = [
            {
                "title": (
                    "New Bike Share Station "
                    "Opens Near Blue Moon"
                ),
                "summary": (
                    "A new bike share station has "
                    "been added near the apartment "
                    "community, giving residents "
                    "another convenient option for "
                    "short local trips."
                ),
                "category": "Transportation",
                "source_name": (
                    "Blue Moon Community"
                ),
                "source_url": None,
                "published_at": datetime(
                    2026,
                    10,
                    9,
                    8,
                    30,
                ),
            },
            {
                "title": (
                    "Weekend Farmers Market "
                    "Returns Saturday"
                ),
                "summary": (
                    "The nearby weekend farmers "
                    "market returns this Saturday "
                    "with local produce, baked goods, "
                    "food vendors and family activities."
                ),
                "category": "Events",
                "source_name": (
                    "Community Bulletin"
                ),
                "source_url": None,
                "published_at": datetime(
                    2026,
                    10,
                    8,
                    16,
                    0,
                ),
            },
            {
                "title": (
                    "Expanded Evening Bus Service"
                ),
                "summary": (
                    "Local transit service has added "
                    "additional evening trips on "
                    "selected routes serving the "
                    "surrounding neighborhood."
                ),
                "category": "Transportation",
                "source_name": (
                    "Community Transit Update"
                ),
                "source_url": None,
                "published_at": datetime(
                    2026,
                    10,
                    7,
                    10,
                    15,
                ),
            },
            {
                "title": (
                    "Community Cleanup Day "
                    "Scheduled for October 17"
                ),
                "summary": (
                    "Residents and nearby neighbors "
                    "are invited to participate in "
                    "a community cleanup event on "
                    "October 17."
                ),
                "category": "Community",
                "source_name": (
                    "Neighborhood Association"
                ),
                "source_url": None,
                "published_at": datetime(
                    2026,
                    10,
                    6,
                    13,
                    0,
                ),
            },
        ]

        for item in community_news:

            existing = db.scalar(
                select(
                    CommunityNews
                ).where(
                    CommunityNews.title
                    == item["title"]
                )
            )

            if existing is None:

                db.add(
                    CommunityNews(
                        title=item[
                            "title"
                        ],
                        summary=item[
                            "summary"
                        ],
                        category=item[
                            "category"
                        ],
                        source_name=item[
                            "source_name"
                        ],
                        source_url=item[
                            "source_url"
                        ],
                        published_at=item[
                            "published_at"
                        ],
                        is_active=True,
                    )
                )

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