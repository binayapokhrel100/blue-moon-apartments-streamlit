
"""Blue Moon Apartments community news service.

Provides category validation and resident-visible
community news. Publication times use naive UTC.
"""

from datetime import datetime, timezone

from sqlalchemy import or_, select

from database.db import get_db_session
from database.models import CommunityNews


# ==================================================
# VALID COMMUNITY NEWS CATEGORIES
# ==================================================

VALID_NEWS_CATEGORIES = {
    "Community",
    "Transportation",
    "Events",
    "Safety",
    "Lifestyle",
    "Local Services",
}


# ==================================================
# UTC DATE AND TIME
# ==================================================

def _utc_now() -> datetime:
    """Return naive UTC consistent with admin content records."""

    return datetime.now(
        timezone.utc
    ).replace(tzinfo=None)


# ==================================================
# VALIDATE COMMUNITY NEWS
# ==================================================

def validate_community_news(
    title: str,
    summary: str,
    category: str,
) -> None:
    """Validate community news content and category."""

    if len(title.strip()) < 4:
        raise ValueError(
            "News title must contain "
            "at least 4 characters."
        )

    if len(summary.strip()) < 10:
        raise ValueError(
            "News summary must contain "
            "at least 10 characters."
        )

    if category not in VALID_NEWS_CATEGORIES:
        raise ValueError(
            "Invalid community news category."
        )


# ==================================================
# COMMON RESIDENT VISIBILITY FILTER
# ==================================================

def _visible_news_conditions(
    now: datetime,
) -> tuple:
    """
    Return the conditions required for
    an item to appear in the resident portal.

    Active news must not have a future
    publication date.

    Older active records without a publication
    date remain supported.
    """

    return (
        CommunityNews.is_active.is_(True),

        or_(
            CommunityNews.published_at.is_(
                None
            ),
            CommunityNews.published_at <= now,
        ),
    )


# ==================================================
# GET ACTIVE COMMUNITY NEWS
# ==================================================

def get_active_community_news() -> list[dict]:
    """Return community news visible to residents."""

    now = _utc_now()

    with get_db_session() as db:

        statement = (
            select(CommunityNews)
            .where(
                *_visible_news_conditions(now)
            )
            .order_by(
                CommunityNews.published_at.desc(),
                CommunityNews.id.desc(),
            )
        )

        news_items = db.scalars(
            statement
        ).all()

        return [
            _news_to_dict(item)
            for item in news_items
        ]


# ==================================================
# GET COMMUNITY NEWS BY CATEGORY
# ==================================================

def get_community_news_by_category(
    category: str,
) -> list[dict]:
    """
    Return resident-visible community news
    in the requested category.

    Hidden and future-dated items are excluded.
    """

    now = _utc_now()

    with get_db_session() as db:

        statement = (
            select(CommunityNews)
            .where(
                *_visible_news_conditions(now),
                CommunityNews.category == category,
            )
            .order_by(
                CommunityNews.published_at.desc(),
                CommunityNews.id.desc(),
            )
        )

        news_items = db.scalars(
            statement
        ).all()

        return [
            _news_to_dict(item)
            for item in news_items
        ]


# ==================================================
# SERIALIZE COMMUNITY NEWS
# ==================================================

def _news_to_dict(
    item: CommunityNews,
) -> dict:
    """Convert a community news model into a dictionary."""

    return {
        "id": item.id,
        "title": item.title,
        "summary": item.summary,
        "category": item.category,
        "source_name": item.source_name,
        "source_url": item.source_url,
        "published_at": item.published_at,
        "is_active": item.is_active,
    }
