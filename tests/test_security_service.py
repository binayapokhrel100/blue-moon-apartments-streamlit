import pytest

from services.security_service import (
    validate_new_password,
)


def test_valid_strong_password():

    validate_new_password(
        "BlueMoon2026!",
        "BlueMoon2026!",
    )


def test_password_mismatch():

    with pytest.raises(ValueError):

        validate_new_password(
            "BlueMoon2026!",
            "BlueMoon2027!",
        )


def test_short_password():

    with pytest.raises(ValueError):

        validate_new_password(
            "Moon1!",
            "Moon1!",
        )


def test_uppercase_required():

    with pytest.raises(ValueError):

        validate_new_password(
            "bluemoon2026!",
            "bluemoon2026!",
        )


def test_lowercase_required():

    with pytest.raises(ValueError):

        validate_new_password(
            "BLUEMOON2026!",
            "BLUEMOON2026!",
        )


def test_number_required():

    with pytest.raises(ValueError):

        validate_new_password(
            "BlueMoonSecurity!",
            "BlueMoonSecurity!",
        )


def test_special_character_required():

    with pytest.raises(ValueError):

        validate_new_password(
            "BlueMoon2026",
            "BlueMoon2026",
        )