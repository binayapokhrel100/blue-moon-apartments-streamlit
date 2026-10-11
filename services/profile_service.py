import re

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from database.db import get_db_session
from database.models import (
    ResidentProfile,
    User,
)


VALID_CONTACT_METHODS = {
    "Email",
    "Phone",
    "SMS",
}


EMAIL_PATTERN = re.compile(
    r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
)


def _validate_phone(
    phone: str,
    field_name: str,
) -> None:

    if not phone.strip():
        return

    digits = re.sub(
        r"\D",
        "",
        phone,
    )

    if not 10 <= len(digits) <= 15:
        raise ValueError(
            f"{field_name} must contain "
            "between 10 and 15 digits."
        )


def validate_profile_update(
    first_name: str,
    last_name: str,
    email: str,
    phone: str,
    emergency_contact_name: str,
    emergency_contact_phone: str,
    preferred_contact_method: str,
) -> None:

    if len(first_name.strip()) < 2:
        raise ValueError(
            "First name must contain "
            "at least 2 characters."
        )

    if len(last_name.strip()) < 2:
        raise ValueError(
            "Last name must contain "
            "at least 2 characters."
        )

    cleaned_email = email.strip().lower()

    if not EMAIL_PATTERN.fullmatch(
        cleaned_email
    ):
        raise ValueError(
            "Please enter a valid email address."
        )

    _validate_phone(
        phone,
        "Phone number",
    )

    emergency_name = (
        emergency_contact_name.strip()
    )

    emergency_phone = (
        emergency_contact_phone.strip()
    )

    if emergency_name and not emergency_phone:
        raise ValueError(
            "Please provide a phone number "
            "for the emergency contact."
        )

    if emergency_phone and not emergency_name:
        raise ValueError(
            "Please provide a name for "
            "the emergency contact."
        )

    _validate_phone(
        emergency_phone,
        "Emergency contact phone",
    )

    if (
        preferred_contact_method
        not in VALID_CONTACT_METHODS
    ):
        raise ValueError(
            "Invalid preferred contact method."
        )


def get_profile(
    user_id: int,
) -> dict | None:

    with get_db_session() as db:

        statement = (
            select(User)
            .options(
                joinedload(
                    User.apartment
                ),
                joinedload(
                    User.resident_profile
                ),
            )
            .where(
                User.id == user_id
            )
        )

        user = db.scalar(
            statement
        )

        if user is None:
            return None

        return _user_to_profile_dict(
            user
        )


def update_profile(
    user_id: int,
    first_name: str,
    last_name: str,
    email: str,
    phone: str,
    emergency_contact_name: str,
    emergency_contact_phone: str,
    preferred_contact_method: str,
) -> dict:

    validate_profile_update(
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=phone,
        emergency_contact_name=(
            emergency_contact_name
        ),
        emergency_contact_phone=(
            emergency_contact_phone
        ),
        preferred_contact_method=(
            preferred_contact_method
        ),
    )

    cleaned_email = (
        email.strip().lower()
    )

    with get_db_session() as db:

        statement = (
            select(User)
            .options(
                joinedload(
                    User.apartment
                ),
                joinedload(
                    User.resident_profile
                ),
            )
            .where(
                User.id == user_id
            )
        )

        user = db.scalar(
            statement
        )

        if user is None:
            raise ValueError(
                "Resident account was not found."
            )

        duplicate_email = db.scalar(
            select(User).where(
                func.lower(
                    User.email
                ) == cleaned_email,
                User.id != user_id,
            )
        )

        if duplicate_email is not None:
            raise ValueError(
                "That email address is already "
                "associated with another account."
            )

        user.first_name = (
            first_name.strip()
        )

        user.last_name = (
            last_name.strip()
        )

        user.email = cleaned_email

        user.phone = (
            phone.strip()
            or None
        )

        if user.resident_profile is None:

            profile = ResidentProfile(
                user_id=user.id,
            )

            db.add(profile)

            user.resident_profile = profile

        user.resident_profile.emergency_contact_name = (
            emergency_contact_name.strip()
            or None
        )

        user.resident_profile.emergency_contact_phone = (
            emergency_contact_phone.strip()
            or None
        )

        user.resident_profile.preferred_contact_method = (
            preferred_contact_method
        )

        db.flush()

        return _user_to_profile_dict(
            user
        )


def _user_to_profile_dict(
    user: User,
) -> dict:

    profile = user.resident_profile

    apartment_unit = None

    if user.apartment is not None:
        apartment_unit = (
            user.apartment.unit_number
        )

    return {
        "id": user.id,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "full_name": user.full_name,
        "email": user.email,
        "phone": user.phone or "",
        "role": user.role,
        "apartment_unit": apartment_unit,
        "emergency_contact_name": (
            profile.emergency_contact_name
            if profile
            else ""
        ),
        "emergency_contact_phone": (
            profile.emergency_contact_phone
            if profile
            else ""
        ),
        "preferred_contact_method": (
            profile.preferred_contact_method
            if profile
            else "Email"
        ),
    }