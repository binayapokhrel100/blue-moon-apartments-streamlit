import pytest

from services.announcement_service import (
    validate_announcement,
)


def test_valid_announcement():

    validate_announcement(
        title="Pool Maintenance",
        message=(
            "The community pool will "
            "be temporarily closed."
        ),
        category="Maintenance",
        priority="Important",
    )


def test_short_title_rejected():

    with pytest.raises(ValueError):

        validate_announcement(
            title="Hi",
            message=(
                "This announcement contains "
                "enough text."
            ),
            category="General",
            priority="Normal",
        )


def test_invalid_priority_rejected():

    with pytest.raises(ValueError):

        validate_announcement(
            title="Pool Maintenance",
            message=(
                "The community pool will "
                "be temporarily closed."
            ),
            category="Maintenance",
            priority="Critical",
        )


def test_invalid_category_rejected():

    with pytest.raises(ValueError):

        validate_announcement(
            title="Pool Maintenance",
            message=(
                "The community pool will "
                "be temporarily closed."
            ),
            category="Unknown",
            priority="Normal",
        )