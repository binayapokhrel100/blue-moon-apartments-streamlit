import pytest

from services.profile_service import (
    validate_profile_update,
)


def test_valid_profile():

    validate_profile_update(
        first_name="Sarah",
        last_name="Mitchell",
        email=(
            "sarah.mitchell@example.com"
        ),
        phone="214-555-0188",
        emergency_contact_name=(
            "Daniel Mitchell"
        ),
        emergency_contact_phone=(
            "214-555-0129"
        ),
        preferred_contact_method=(
            "Email"
        ),
    )


def test_invalid_email_rejected():

    with pytest.raises(ValueError):

        validate_profile_update(
            first_name="Sarah",
            last_name="Mitchell",
            email="invalid-email",
            phone="214-555-0188",
            emergency_contact_name=(
                "Daniel Mitchell"
            ),
            emergency_contact_phone=(
                "214-555-0129"
            ),
            preferred_contact_method=(
                "Email"
            ),
        )


def test_short_first_name_rejected():

    with pytest.raises(ValueError):

        validate_profile_update(
            first_name="S",
            last_name="Mitchell",
            email="sarah@example.com",
            phone="214-555-0188",
            emergency_contact_name=(
                "Daniel Mitchell"
            ),
            emergency_contact_phone=(
                "214-555-0129"
            ),
            preferred_contact_method=(
                "Email"
            ),
        )


def test_invalid_phone_rejected():

    with pytest.raises(ValueError):

        validate_profile_update(
            first_name="Sarah",
            last_name="Mitchell",
            email="sarah@example.com",
            phone="123",
            emergency_contact_name=(
                "Daniel Mitchell"
            ),
            emergency_contact_phone=(
                "214-555-0129"
            ),
            preferred_contact_method=(
                "Email"
            ),
        )


def test_emergency_name_requires_phone():

    with pytest.raises(ValueError):

        validate_profile_update(
            first_name="Sarah",
            last_name="Mitchell",
            email="sarah@example.com",
            phone="214-555-0188",
            emergency_contact_name=(
                "Daniel Mitchell"
            ),
            emergency_contact_phone="",
            preferred_contact_method=(
                "Email"
            ),
        )


def test_emergency_phone_requires_name():

    with pytest.raises(ValueError):

        validate_profile_update(
            first_name="Sarah",
            last_name="Mitchell",
            email="sarah@example.com",
            phone="214-555-0188",
            emergency_contact_name="",
            emergency_contact_phone=(
                "214-555-0129"
            ),
            preferred_contact_method=(
                "Email"
            ),
        )


def test_invalid_contact_method():

    with pytest.raises(ValueError):

        validate_profile_update(
            first_name="Sarah",
            last_name="Mitchell",
            email="sarah@example.com",
            phone="214-555-0188",
            emergency_contact_name=(
                "Daniel Mitchell"
            ),
            emergency_contact_phone=(
                "214-555-0129"
            ),
            preferred_contact_method=(
                "Carrier Pigeon"
            ),
        )