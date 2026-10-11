import pytest

from services.community_news_service import (
    validate_community_news,
)


def test_valid_community_news():

    validate_community_news(
        title="New Bike Share Station",
        summary=(
            "A new bike share station "
            "has opened nearby."
        ),
        category="Transportation",
    )


def test_short_news_title_rejected():

    with pytest.raises(ValueError):

        validate_community_news(
            title="Hi",
            summary=(
                "A new community update "
                "was published today."
            ),
            category="Community",
        )


def test_short_summary_rejected():

    with pytest.raises(ValueError):

        validate_community_news(
            title="Community Update",
            summary="Short",
            category="Community",
        )


def test_invalid_news_category_rejected():

    with pytest.raises(ValueError):

        validate_community_news(
            title="Community Update",
            summary=(
                "A new community update "
                "was published today."
            ),
            category="Unknown",
        )