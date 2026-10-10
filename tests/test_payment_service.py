from decimal import Decimal

import pytest

from services.payment_service import (
    generate_confirmation_number,
    validate_payment_amount,
)


def test_confirmation_number_format():

    confirmation = (
        generate_confirmation_number()
    )

    assert confirmation.startswith(
        "BMP-"
    )


def test_valid_payment_amount():

    validate_payment_amount(
        Decimal("500.00"),
        Decimal("1250.00"),
    )


def test_zero_payment_rejected():

    with pytest.raises(ValueError):

        validate_payment_amount(
            Decimal("0.00"),
            Decimal("1250.00"),
        )


def test_negative_payment_rejected():

    with pytest.raises(ValueError):

        validate_payment_amount(
            Decimal("-10.00"),
            Decimal("1250.00"),
        )


def test_overpayment_rejected():

    with pytest.raises(ValueError):

        validate_payment_amount(
            Decimal("1300.00"),
            Decimal("1250.00"),
        )