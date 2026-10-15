
"""Read-only database queries for Blue Moon's admin overview (Sprint 09)."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload
from services.admin_management_service import _require_admin

from database.db import get_db_session
from database.models import (
    Announcement,
    Apartment,
    MaintenanceRequest,
    Payment,
    User,
)


def get_admin_dashboard_data(admin_user_id: int) -> dict:
    """Return summary statistics and recent activity from the real database."""

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    month_start = datetime(now.year, now.month, 1)
    if now.month == 12:
        next_month_start = datetime(now.year + 1, 1, 1)
    else:
        next_month_start = datetime(now.year, now.month + 1, 1)

    with get_db_session() as db:
        # The overview combines multiple sensitive datasets.
        # The caller must be authorized to read all of them.

        for permission in (
            "overview.read",
            "tenants.read",
            "apartments.read",
            "maintenance.read",
            "payments.read",
            "announcements.read",
        ):
            _require_admin(
                db,
                admin_user_id,
                permission=permission,
            )
        total_apartments = db.scalar(
            select(func.count(Apartment.id))
        ) or 0

        occupied_units = db.scalar(
            select(func.count(Apartment.id)).where(
                Apartment.is_occupied.is_(True)
            )
        ) or 0

        active_residents = db.scalar(
            select(func.count(User.id)).where(
                func.lower(User.role) == "resident",
                User.is_active.is_(True),
            )
        ) or 0

        open_maintenance = db.scalar(
            select(func.count(MaintenanceRequest.id)).where(
                func.lower(
                    func.trim(MaintenanceRequest.status)
                ).not_in(("completed", "cancelled", "canceled"))
            )
        ) or 0

        monthly_collected = db.scalar(
            select(func.sum(Payment.amount)).where(
                func.lower(Payment.status) == "confirmed",
                Payment.paid_at >= month_start,
                Payment.paid_at < next_month_start,
            )
        ) or Decimal("0.00")

        notice_filters = (
            Announcement.is_published.is_(True),
            Announcement.published_at <= now,
            or_(
                Announcement.expires_at.is_(None),
                Announcement.expires_at >= now,
            ),
        )

        published_notices = db.scalar(
            select(func.count(Announcement.id)).where(*notice_filters)
        ) or 0

        maintenance_records = db.scalars(
            select(MaintenanceRequest)
            .options(
                joinedload(MaintenanceRequest.resident),
                joinedload(MaintenanceRequest.apartment),
            )
            .order_by(
                MaintenanceRequest.created_at.desc(),
                MaintenanceRequest.id.desc(),
            )
            .limit(5)
        ).all()

        payment_records = db.scalars(
            select(Payment)
            .options(joinedload(Payment.resident))
            .order_by(Payment.paid_at.desc(), Payment.id.desc())
            .limit(5)
        ).all()

        announcement_records = db.scalars(
            select(Announcement)
            .where(*notice_filters)
            .order_by(
                Announcement.published_at.desc(),
                Announcement.id.desc(),
            )
            .limit(4)
        ).all()

        maintenance = [
            {
                "request_number": item.request_number,
                "category": item.category,
                "status": item.status,
                "urgency": item.urgency,
                "unit": (
                    item.apartment.unit_number
                    if item.apartment else "Unassigned"
                ),
                "resident": (
                    item.resident.full_name
                    if item.resident else "Unknown resident"
                ),
                "created_at": item.created_at,
            }
            for item in maintenance_records
        ]

        payments = [
            {
                "resident": (
                    item.resident.full_name
                    if item.resident else "Unknown resident"
                ),
                "amount": item.amount,
                "status": item.status,
                "method": item.payment_method,
                "paid_at": item.paid_at,
            }
            for item in payment_records
        ]

        announcements = [
            {
                "title": item.title,
                "category": item.category,
                "published_at": item.published_at,
            }
            for item in announcement_records
        ]

    occupancy_rate = (
        round(100 * occupied_units / total_apartments, 1)
        if total_apartments else 0.0
    )

    return {
        "total_apartments": total_apartments,
        "occupied_units": occupied_units,
        "vacant_units": max(0, total_apartments - occupied_units),
        "occupancy_rate": occupancy_rate,
        "active_residents": active_residents,
        "open_maintenance": open_maintenance,
        "monthly_collected": monthly_collected,
        "published_notices": published_notices,
        "month_label": now.strftime("%B %Y"),
        "maintenance": maintenance,
        "payments": payments,
        "announcements": announcements,
        "updated_at": now,
    }
