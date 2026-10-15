
"""Blue Moon Apartments announcement service.

Handles announcement validation, resident visibility,
and legacy announcement creation with notifications.
All database publication timestamps use naive UTC.
"""

from datetime import datetime, timezone

from sqlalchemy import or_, select

from database.db import get_db_session
from database.models import (
    Announcement,
    Notification,
    User,
)


# ==================================================
# VALID ANNOUNCEMENT VALUES
# ==================================================

VALID_ANNOUNCEMENT_CATEGORIES = {
    "General",
    "Maintenance",
    "Community",
    "Safety",
    "Events",
    "Management",
}

VALID_PRIORITIES = {
    "Normal",
    "Important",
    "Urgent",
}


# ==================================================
# UTC DATE AND TIME
# ==================================================

def _utc_now() -> datetime:
    """Return naive UTC consistent with admin content records."""

    return datetime.now(
        timezone.utc
    ).replace(tzinfo=None)


def _normalize_utc(
    value: datetime | None,
) -> datetime | None:
    """Convert timezone-aware datetimes to naive UTC."""

    if value is None:
        return None

    if value.tzinfo is not None:
        return value.astimezone(
            timezone.utc
        ).replace(tzinfo=None)

    # Existing database convention:
    # a naive datetime represents UTC.
    return value


# ==================================================
# VALIDATE ANNOUNCEMENT
# ==================================================

def validate_announcement(
    title: str,
    message: str,
    category: str,
    priority: str,
) -> None:
    """Validate announcement text, category and priority."""

    if len(title.strip()) < 4:
        raise ValueError(
            "Announcement title must contain "
            "at least 4 characters."
        )

    if len(message.strip()) < 10:
        raise ValueError(
            "Announcement message must contain "
            "at least 10 characters."
        )

    if category not in VALID_ANNOUNCEMENT_CATEGORIES:
        raise ValueError(
            "Invalid announcement category."
        )

    if priority not in VALID_PRIORITIES:
        raise ValueError(
            "Invalid announcement priority."
        )


# ==================================================
# CREATE ANNOUNCEMENT
# ==================================================

def create_announcement(
    title: str,
    message: str,
    category: str = "General",
    priority: str = "Normal",
    expires_at: datetime | None = None,
    notify_residents: bool = True,
) -> dict:
    """
    Legacy/internal announcement creation workflow.

    This function creates a published announcement
    and optionally notifies active residents.

    Do not expose this function directly through
    unprivileged resident-facing pages or endpoints.
    Use admin_content_service for authorized admin writes.
    """

    validate_announcement(
        title=title,
        message=message,
        category=category,
        priority=priority,
    )

    now = _utc_now()

    normalized_expiration = _normalize_utc(
        expires_at
    )

    # ------------------------------------------
    # VALIDATE EXPIRATION
    # ------------------------------------------

    if (
        normalized_expiration is not None
        and normalized_expiration <= now
    ):
        raise ValueError(
            "Announcement expiration must "
            "be in the future."
        )

    # ------------------------------------------
    # CREATE ANNOUNCEMENT
    # ------------------------------------------

    with get_db_session() as db:

        announcement = Announcement(
            title=title.strip(),
            message=message.strip(),
            category=category,
            priority=priority,
            is_published=True,
            published_at=now,
            expires_at=normalized_expiration,
        )

        db.add(announcement)
        db.flush()

        # --------------------------------------
        # OPTIONAL RESIDENT NOTIFICATIONS
        # --------------------------------------

        if notify_residents:

            residents = db.scalars(
                select(User).where(
                    User.role == "resident",
                    User.is_active.is_(True),
                )
            ).all()

            for resident in residents:

                notification = Notification(
                    user_id=resident.id,
                    title=(
                        "New Announcement: "
                        f"{announcement.title}"
                    ),
                    message=announcement.message,
                    notification_type="announcement",
                    is_read=False,
                    is_alert=(
                        priority == "Urgent"
                    ),
                )

                db.add(notification)

        db.flush()

        return _announcement_to_dict(
            announcement
        )


# ==================================================
# GET ACTIVE ANNOUNCEMENTS
# ==================================================

def get_active_announcements() -> list[dict]:
    """
    Return announcements currently visible
    to residents.

    A visible announcement must:
    1. Be published.
    2. Have reached its publication time.
    3. Not have expired.

    Null publication timestamps are supported
    for compatibility with older published records.
    """

    now = _utc_now()

    with get_db_session() as db:

        statement = (
            select(Announcement)
            .where(

                # Must be published.
                Announcement.is_published.is_(
                    True
                ),

                # Do not show future-dated content.
                or_(
                    Announcement.published_at.is_(
                        None
                    ),
                    Announcement.published_at <= now,
                ),

                # Do not show expired content.
                or_(
                    Announcement.expires_at.is_(
                        None
                    ),
                    Announcement.expires_at >= now,
                ),
            )
            .order_by(
                Announcement.published_at.desc(),
                Announcement.id.desc(),
            )
        )

        announcements = db.scalars(
            statement
        ).all()

        return [
            _announcement_to_dict(item)
            for item in announcements
        ]


# ==================================================
# GET ALL ANNOUNCEMENTS
# ==================================================

def get_all_announcements() -> list[dict]:
    """
    Legacy/internal unrestricted listing.

    WARNING: Includes unpublished announcements.
    Do not use this function on resident pages.
    """

    with get_db_session() as db:

        statement = (
            select(Announcement)
            .order_by(
                Announcement.published_at.desc(),
                Announcement.id.desc(),
            )
        )

        announcements = db.scalars(
            statement
        ).all()

        return [
            _announcement_to_dict(item)
            for item in announcements
        ]


# ==================================================
# GET ANNOUNCEMENT BY ID
# ==================================================

def get_announcement(
    announcement_id: int,
) -> dict | None:
    """
    Legacy/internal lookup by ID.

    WARNING: May return an unpublished item.
    Do not expose this unrestricted lookup
    directly through resident-facing pages.
    """

    with get_db_session() as db:

        announcement = db.get(
            Announcement,
            announcement_id,
        )

        if announcement is None:
            return None

        return _announcement_to_dict(
            announcement
        )


# ==================================================
# SERIALIZE ANNOUNCEMENT
# ==================================================

def _announcement_to_dict(
    announcement: Announcement,
) -> dict:
    """Convert an announcement database model to a dictionary."""

    return {
        "id": announcement.id,
        "title": announcement.title,
        "message": announcement.message,
        "category": announcement.category,
        "priority": announcement.priority,
        "is_published": announcement.is_published,
        "published_at": announcement.published_at,
        "expires_at": announcement.expires_at,
        "created_at": announcement.created_at,
    }
