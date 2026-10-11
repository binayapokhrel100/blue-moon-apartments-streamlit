from datetime import date

import pytest

from services.lease_service import (
    calculate_days_remaining,
    calculate_lease_progress,
)


def test_lease_progress_before_start():

    progress = calculate_lease_progress(
        start_date=date(
            2026,
            6,
            1,
        ),
        end_date=date(
            2027,
            6,
            1,
        ),
        as_of=date(
            2026,
            5,
            1,
        ),
    )

    assert progress == 0


def test_lease_progress_after_end():

    progress = calculate_lease_progress(
        start_date=date(
            2026,
            6,
            1,
        ),
        end_date=date(
            2027,
            6,
            1,
        ),
        as_of=date(
            2027,
            7,
            1,
        ),
    )

    assert progress == 100


def test_lease_progress_midpoint():

    progress = calculate_lease_progress(
        start_date=date(
            2026,
            1,
            1,
        ),
        end_date=date(
            2026,
            1,
            11,
        ),
        as_of=date(
            2026,
            1,
            6,
        ),
    )

    assert progress == 50


def test_invalid_lease_dates():

    with pytest.raises(ValueError):

        calculate_lease_progress(
            start_date=date(
                2026,
                6,
                1,
            ),
            end_date=date(
                2026,
                6,
                1,
            ),
        )


def test_days_remaining():

    remaining = (
        calculate_days_remaining(
            end_date=date(
                2026,
                10,
                20,
            ),
            as_of=date(
                2026,
                10,
                10,
            ),
        )
    )

    assert remaining == 10


def test_expired_lease_has_zero_days():

    remaining = (
        calculate_days_remaining(
            end_date=date(
                2026,
                9,
                1,
            ),
            as_of=date(
                2026,
                10,
                10,
            ),
        )
    )

    assert remaining == 0