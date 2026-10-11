from sqlalchemy import select

from database.db import get_db_session
from database.models import CommunityNews


VALID_NEWS_CATEGORIES = {
    "Community",
    "Transportation",
    "Events",
    "Safety",
    "Lifestyle",
    "Local Services",
}


def validate_community_news(
    title: str,
    summary: str,
    category: str,
) -> None:

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


def get_active_community_news() -> list[dict]:

    with get_db_session() as db:

        statement = (
            select(CommunityNews)
            .where(
                CommunityNews.is_active.is_(True)
            )
            .order_by(
                CommunityNews.published_at.desc()
            )
        )

        news_items = db.scalars(
            statement
        ).all()

        return [
            _news_to_dict(item)
            for item in news_items
        ]


def get_community_news_by_category(
    category: str,
) -> list[dict]:

    with get_db_session() as db:

        statement = (
            select(CommunityNews)
            .where(
                CommunityNews.is_active.is_(True),
                CommunityNews.category == category,
            )
            .order_by(
                CommunityNews.published_at.desc()
            )
        )

        news_items = db.scalars(
            statement
        ).all()

        return [
            _news_to_dict(item)
            for item in news_items
        ]


def _news_to_dict(
    item: CommunityNews,
) -> dict:

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