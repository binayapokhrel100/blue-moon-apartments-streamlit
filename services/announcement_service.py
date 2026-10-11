from datetime import datetime

from sqlalchemy import or_, select

from database.db import get_db_session
from database.models import (
    Announcement,
    Notification,
    User,
)


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


def validate_announcement(
    title: str,
    message: str,
    category: str,
    priority: str,
) -> None:

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


def create_announcement(
    title: str,
    message: str,
    category: str = "General",
    priority: str = "Normal",
    expires_at: datetime | None = None,
    notify_residents: bool = True,
) -> dict:

    validate_announcement(
        title=title,
        message=message,
        category=category,
        priority=priority,
    )

    now = datetime.now()

    if (
        expires_at is not None
        and expires_at <= now
    ):
        raise ValueError(
            "Announcement expiration must "
            "be in the future."
        )

    with get_db_session() as db:

        announcement = Announcement(
            title=title.strip(),
            message=message.strip(),
            category=category,
            priority=priority,
            is_published=True,
            published_at=now,
            expires_at=expires_at,
        )

        db.add(announcement)
        db.flush()

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


def get_active_announcements() -> list[dict]:

    now = datetime.now()

    with get_db_session() as db:

        statement = (
            select(Announcement)
            .where(
                Announcement.is_published.is_(True),
                or_(
                    Announcement.expires_at.is_(None),
                    Announcement.expires_at >= now,
                ),
            )
            .order_by(
                Announcement.published_at.desc()
            )
        )

        announcements = db.scalars(
            statement
        ).all()

        return [
            _announcement_to_dict(item)
            for item in announcements
        ]


def get_all_announcements() -> list[dict]:

    with get_db_session() as db:

        statement = (
            select(Announcement)
            .order_by(
                Announcement.published_at.desc()
            )
        )

        announcements = db.scalars(
            statement
        ).all()

        return [
            _announcement_to_dict(item)
            for item in announcements
        ]


def get_announcement(
    announcement_id: int,
) -> dict | None:

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


def _announcement_to_dict(
    announcement: Announcement,
) -> dict:

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