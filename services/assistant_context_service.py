
"""Read-only data access for Blue Moon Assistant.

Resident-owned queries are always filtered by user ID.
The caller must use the authenticated session's user ID.
"""

from datetime import date, datetime

from sqlalchemy import or_, select

from database.db import get_db_session
from database.models import (
    Announcement,
    Apartment,
    CommunityNews,
    Lease,
    MaintenanceRequest,
    Payment,
    User,
)


def _date_text(value: date | datetime | None) -> str | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.date().isoformat()

    return value.isoformat()


def _amount_text(value) -> str | None:
    if value is None:
        return None

    return str(value)


def build_assistant_context(user_id: int) -> dict:
    """Read the current resident's information for the chatbot."""

    if (
        isinstance(user_id, bool)
        or not isinstance(user_id, int)
        or user_id < 1
    ):
        raise ValueError(
            "A valid resident user ID is required."
        )

    with get_db_session() as db:

        # ======================================
        # VERIFY RESIDENT
        # ======================================

        user = db.scalar(
            select(User).where(
                User.id == user_id,
                User.is_active.is_(True),
            )
        )

        if user is None or user.role != "resident":
            raise PermissionError(
                "An active resident account is required."
            )

        # ======================================
        # APARTMENT
        # ======================================

        apartment = None

        if user.apartment_id is not None:
            apartment = db.scalar(
                select(Apartment).where(
                    Apartment.id == user.apartment_id
                )
            )

        # ======================================
        # ACTIVE LEASE
        # ======================================

        lease = db.scalar(
            select(Lease)
            .where(
                Lease.resident_id == user.id,
                Lease.status == "active",
            )
            .order_by(Lease.start_date.desc())
            .limit(1)
        )

        # ======================================
        # RECENT PAYMENTS
        # ======================================

        payments = db.scalars(
            select(Payment)
            .where(
                Payment.resident_id == user.id
            )
            .order_by(
                Payment.paid_at.desc(),
                Payment.id.desc(),
            )
            .limit(5)
        ).all()

        # ======================================
        # MAINTENANCE REQUESTS
        # ======================================

        requests = db.scalars(
            select(MaintenanceRequest)
            .where(
                MaintenanceRequest.resident_id == user.id
            )
            .order_by(
                MaintenanceRequest.created_at.desc()
            )
            .limit(5)
        ).all()

        # ======================================
        # PUBLISHED ANNOUNCEMENTS
        # ======================================

        now = datetime.utcnow()

        announcements = db.scalars(
            select(Announcement)
            .where(
                Announcement.is_published.is_(True),
                or_(
                    Announcement.published_at.is_(None),
                    Announcement.published_at <= now,
                ),
                or_(
                    Announcement.expires_at.is_(None),
                    Announcement.expires_at >= now,
                ),
            )
            .order_by(
                Announcement.published_at.desc()
            )
            .limit(5)
        ).all()

        # ======================================
        # COMMUNITY NEWS
        # ======================================

        news = db.scalars(
            select(CommunityNews)
            .where(
                CommunityNews.is_active.is_(True)
            )
            .order_by(
                CommunityNews.published_at.desc()
            )
            .limit(5)
        ).all()

        # ======================================
        # SERIALIZE DATABASE RECORDS
        # ======================================

        return {
            "resident": {
                "first_name": user.first_name or "Resident",
                "unit_number": (
                    apartment.unit_number
                    if apartment
                    else None
                ),
            },

            "lease": (
                {
                    "start_date": _date_text(
                        lease.start_date
                    ),
                    "end_date": _date_text(
                        lease.end_date
                    ),
                    "monthly_rent": _amount_text(
                        lease.monthly_rent
                    ),
                    "security_deposit": _amount_text(
                        lease.security_deposit
                    ),
                    "status": lease.status,
                }
                if lease
                else None
            ),

            "payments": [
                {
                    "payment_month": _date_text(
                        item.payment_month
                    ),
                    "amount": _amount_text(
                        item.amount
                    ),
                    "status": item.status,
                    "paid_at": _date_text(
                        item.paid_at
                    ),
                }
                for item in payments
            ],

            "maintenance": [
                {
                    "request_number": item.request_number,
                    "category": item.category,
                    "status": item.status,
                }
                for item in requests
            ],

            "announcements": [
                {
                    "title": item.title,
                    "message": item.message,
                }
                for item in announcements
            ],

            "community_news": [
                {
                    "title": item.title,
                    "summary": item.summary,
                }
                for item in news
            ],
        }
