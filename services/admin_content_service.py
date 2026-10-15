
"""Authorized announcement and community-news management for Sprint 09."""

from datetime import date, datetime, time, timezone
from urllib.parse import urlsplit

from sqlalchemy import func, select

from database.db import get_db_session
from database.models import (
    AdminEmployee,
    Announcement,
    CommunityNews,
    User,
)


# ==================================================
# CONSTANTS
# ==================================================

PRIORITIES = (
    "Normal",
    "Important",
    "Urgent",
)


# ==================================================
# TIME HELPER
# ==================================================

def _utc_now() -> datetime:
    """Return naive UTC to match the existing database."""

    return datetime.now(
        timezone.utc
    ).replace(tzinfo=None)


# ==================================================
# AUTHORIZE ADMINISTRATOR
# ==================================================

def _require_admin(
    db,
    admin_user_id: int,
    permission: str,
) -> None:
    """Use the central database-backed role check."""
    from services.admin_management_service import (
        _require_admin as shared_admin_check,
    )
    shared_admin_check(
        db,
        admin_user_id,
        permission=permission,
    )


# ==================================================
# TEXT VALIDATION
# ==================================================

def _required_text(
    value: str,
    label: str,
    limit: int,
) -> str:

    cleaned = (
        value or ""
    ).strip()

    if not cleaned:
        raise ValueError(
            f"{label} is required."
        )

    if len(cleaned) > limit:
        raise ValueError(
            f"{label} must be {limit} characters or fewer."
        )

    return cleaned


def _optional_text(
    value: str,
    label: str,
    limit: int,
) -> str | None:

    cleaned = (
        value or ""
    ).strip()

    if len(cleaned) > limit:
        raise ValueError(
            f"{label} must be {limit} characters or fewer."
        )

    return cleaned or None


# ==================================================
# EXPIRATION DATE
# ==================================================

def _expiration(
    value: str,
) -> datetime | None:
    """
    Optional YYYY-MM-DD date.
    End of selected day, interpreted as UTC.
    """

    raw = (
        value or ""
    ).strip()

    if not raw:
        return None

    try:
        day = date.fromisoformat(
            raw
        )

    except ValueError as exc:
        raise ValueError(
            "Expiration must be YYYY-MM-DD, "
            "or left blank."
        ) from exc

    return datetime.combine(
        day,
        time(23, 59, 59),
    )


# ==================================================
# ANNOUNCEMENT VALIDATION
# ==================================================

def _announcement_fields(
    title: str,
    message: str,
    category: str,
    priority: str,
    expires_on: str,
    published: bool,
) -> dict:

    if priority not in PRIORITIES:
        raise ValueError(
            "Select a valid announcement priority."
        )

    expiry = _expiration(
        expires_on
    )

    if (
        published
        and expiry is not None
        and expiry <= _utc_now()
    ):
        raise ValueError(
            "Published announcements need "
            "a future expiration date."
        )

    return {
        "title": _required_text(
            title, "Title", 255
        ),
        "message": _required_text(
            message, "Message", 10000
        ),
        "category": _required_text(
            category, "Category", 100
        ),
        "priority": priority,
        "expires_at": expiry,
        "is_published": bool(published),
    }


# ==================================================
# COMMUNITY NEWS VALIDATION
# ==================================================

def _news_fields(
    title: str,
    summary: str,
    category: str,
    source_name: str,
    source_url: str,
    active: bool,
) -> dict:

    url = _optional_text(
        source_url,
        "Source URL",
        1000,
    )

    if url:
        parsed = urlsplit(url)

        if (
            parsed.scheme not in {
                "https",
                "http",
            }
            or not parsed.hostname
        ):
            raise ValueError(
                "Source URL must start with "
                "https:// or http:// and "
                "include a hostname."
            )

    return {
        "title": _required_text(
            title, "Headline", 255
        ),
        "summary": _required_text(
            summary, "Summary", 10000
        ),
        "category": _required_text(
            category, "Category", 100
        ),
        "source_name": _optional_text(
            source_name, "Source name", 150
        ),
        "source_url": url,
        "is_active": bool(active),
    }


# ==================================================
# GET ANNOUNCEMENTS
# ==================================================

def get_admin_announcements(
    admin_id: int,
) -> list[dict]:
    """Return the latest 500 announcements."""

    now = _utc_now()

    with get_db_session() as db:

        _require_admin(
            db,
            admin_id,
            permission="announcements.read",
        )

        records = db.scalars(
            select(Announcement)
            .order_by(
                Announcement.created_at.desc(),
                Announcement.id.desc(),
            )
            .limit(500)
        ).all()

        return [
            {
                "id": item.id,
                "title": item.title,
                "message": item.message,
                "category": item.category,
                "priority": item.priority,
                "published": bool(
                    item.is_published
                ),
                "published_at": (
                    item.published_at
                ),
                "expires_at": (
                    item.expires_at
                ),
                "created_at": item.created_at,
                "visibility": (
                    "Draft"
                    if not item.is_published
                    else "Scheduled"
                    if (
                        item.published_at
                        and item.published_at > now
                    )
                    else "Expired"
                    if (
                        item.expires_at
                        and item.expires_at < now
                    )
                    else "Published"
                ),
            }
            for item in records
        ]


# ==================================================
# CREATE ANNOUNCEMENT
# ==================================================

def create_admin_announcement(
    admin_id: int,
    *,
    title: str,
    message: str,
    category: str,
    priority: str,
    expires_on: str,
    published: bool,
) -> int:

    fields = _announcement_fields(
        title,
        message,
        category,
        priority,
        expires_on,
        published,
    )

    with get_db_session() as db:

        _require_admin(
            db,
            admin_id,
            permission="announcements.manage",
        )

        item = Announcement(
            **fields,
            published_at=_utc_now(),
        )

        db.add(item)
        db.flush()

        return item.id


# ==================================================
# UPDATE / PUBLISH / UNPUBLISH ANNOUNCEMENT
# ==================================================

def update_admin_announcement(
    admin_id: int,
    announcement_id: int,
    *,
    title: str,
    message: str,
    category: str,
    priority: str,
    expires_on: str,
    published: bool,
) -> None:

    fields = _announcement_fields(
        title,
        message,
        category,
        priority,
        expires_on,
        published,
    )

    with get_db_session() as db:

        _require_admin(
            db,
            admin_id,
            permission="announcements.manage",
        )

        item = db.get(
            Announcement,
            announcement_id,
        )

        if item is None:
            raise ValueError(
                "Announcement no longer exists. "
                "Refresh the page."
            )

        # Publishing a draft makes it current.

        if (
            published
            and not item.is_published
        ):
            item.published_at = _utc_now()

        for field, value in fields.items():
            setattr(
                item,
                field,
                value,
            )


# ==================================================
# GET COMMUNITY NEWS
# ==================================================

def get_admin_community_news(
    admin_id: int,
) -> list[dict]:
    """Return the latest 500 news records."""

    with get_db_session() as db:

        _require_admin(
            db,
            admin_id,
            permission="news.read",
        )

        records = db.scalars(
            select(CommunityNews)
            .order_by(
                CommunityNews.created_at.desc(),
                CommunityNews.id.desc(),
            )
            .limit(500)
        ).all()

        return [
            {
                "id": item.id,
                "title": item.title,
                "summary": item.summary,
                "category": item.category,
                "source_name": (
                    item.source_name or ""
                ),
                "source_url": (
                    item.source_url or ""
                ),
                "published_at": (
                    item.published_at
                ),
                "active": bool(
                    item.is_active
                ),
                "created_at": (
                    item.created_at
                ),
            }
            for item in records
        ]


# ==================================================
# CREATE COMMUNITY NEWS
# ==================================================

def create_admin_community_news(
    admin_id: int,
    *,
    title: str,
    summary: str,
    category: str,
    source_name: str,
    source_url: str,
    active: bool,
) -> int:

    fields = _news_fields(
        title,
        summary,
        category,
        source_name,
        source_url,
        active,
    )

    with get_db_session() as db:

        _require_admin(
            db,
            admin_id,
            permission="news.manage",
        )

        item = CommunityNews(
            **fields,
            published_at=_utc_now(),
        )

        db.add(item)
        db.flush()

        return item.id


# ==================================================
# UPDATE / ACTIVATE / HIDE COMMUNITY NEWS
# ==================================================

def update_admin_community_news(
    admin_id: int,
    news_id: int,
    *,
    title: str,
    summary: str,
    category: str,
    source_name: str,
    source_url: str,
    active: bool,
) -> None:

    fields = _news_fields(
        title,
        summary,
        category,
        source_name,
        source_url,
        active,
    )

    with get_db_session() as db:

        _require_admin(
            db,
            admin_id,
            permission="news.manage",
        )

        item = db.get(
            CommunityNews,
            news_id,
        )

        if item is None:
            raise ValueError(
                "Community news item no longer exists. "
                "Refresh the page."
            )

        # Reactivated news receives a current
        # publication timestamp.

        if (
            active
            and not item.is_active
        ):
            item.published_at = _utc_now()

        for field, value in fields.items():
            setattr(
                item,
                field,
                value,
            )
