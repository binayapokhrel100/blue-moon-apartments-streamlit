import re

import pytest

from services.maintenance_service import (
    generate_request_number,
    validate_maintenance_request,
)


def test_request_number_format():

    request_number = (
        generate_request_number(
            year=2026
        )
    )

    assert re.fullmatch(
        r"MR-2026-\d{4}",
        request_number,
    )


def test_valid_maintenance_request():

    validate_maintenance_request(
        category="Plumbing",
        description=(
            "The kitchen faucet "
            "is leaking continuously."
        ),
        urgency="Medium",
    )


def test_invalid_category_rejected():

    with pytest.raises(ValueError):

        validate_maintenance_request(
            category="Unknown",
            description=(
                "There is an issue "
                "inside the apartment."
            ),
            urgency="Medium",
        )


def test_short_description_rejected():

    with pytest.raises(ValueError):

        validate_maintenance_request(
            category="Plumbing",
            description="Leak",
            urgency="Medium",
        )


def test_invalid_urgency_rejected():

    with pytest.raises(ValueError):

        validate_maintenance_request(
            category="Plumbing",
            description=(
                "The faucet has been "
                "leaking continuously."
            ),
            urgency="Extreme",
        )