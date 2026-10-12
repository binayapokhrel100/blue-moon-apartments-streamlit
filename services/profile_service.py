
"""Resident profile service for Blue Moon Apartments."""

import re

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from database.db import get_db_session
from database.models import ResidentProfile, User


VALID_CONTACT_METHODS = {
    "Email",
    "Phone",
    "SMS",
}

EMAIL_PATTERN = re.compile(
    r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
)


# ==========================================
# VALIDATION
# ==========================================

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
    *,
    secondary_email: str,
    secondary_phone: str,
    emergency_contact_name: str,
    emergency_contact_phone: str,
    preferred_contact_method: str,
) -> None:

    cleaned_email = secondary_email.strip().lower()

    if cleaned_email:
        if (
            len(cleaned_email) > 255
            or not EMAIL_PATTERN.fullmatch(cleaned_email)
        ):
            raise ValueError(
                "Please enter a valid additional email address."
            )

    if len(secondary_phone.strip()) > 30:
        raise ValueError(
            "Additional phone number is too long."
        )

    _validate_phone(
        secondary_phone,
        "Additional phone number",
    )

    emergency_name = emergency_contact_name.strip()
    emergency_phone = emergency_contact_phone.strip()

    if len(emergency_name) > 150:
        raise ValueError(
            "Emergency contact name is too long."
        )

    if len(emergency_phone) > 30:
        raise ValueError(
            "Emergency contact phone number is too long."
        )

    if bool(emergency_name) != bool(emergency_phone):
        raise ValueError(
            "Enter both the emergency contact "
            "name and phone number."
        )

    _validate_phone(
        emergency_phone,
        "Emergency contact phone",
    )

    if preferred_contact_method not in VALID_CONTACT_METHODS:
        raise ValueError(
            "Invalid preferred contact method."
        )


# ==========================================
# DATABASE HELPERS
# ==========================================

def _find_user(db, user_id: int) -> User | None:

    return db.scalar(
        select(User)
        .options(
            joinedload(User.apartment),
            joinedload(User.resident_profile),
        )
        .where(User.id == user_id)
    )


def _user_to_profile_dict(user: User) -> dict:

    profile = user.resident_profile

    apartment_unit = None

    if user.apartment is not None:
        apartment_unit = user.apartment.unit_number

    return {
        # Primary account details (read-only)
        "id": user.id,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "full_name": user.full_name,
        "email": user.email,
        "phone": user.phone or "",
        "role": user.role,
        "apartment_unit": apartment_unit,

        # Additional contact details
        "secondary_email": (
            profile.secondary_email or ""
            if profile else ""
        ),
        "secondary_phone": (
            profile.secondary_phone or ""
            if profile else ""
        ),

        # Emergency contact
        "emergency_contact_name": (
            profile.emergency_contact_name or ""
            if profile else ""
        ),
        "emergency_contact_phone": (
            profile.emergency_contact_phone or ""
            if profile else ""
        ),

        # Communication preference
        "preferred_contact_method": (
            profile.preferred_contact_method or "Email"
            if profile else "Email"
        ),
    }


# ==========================================
# GET RESIDENT PROFILE
# ==========================================

def get_profile(user_id: int) -> dict | None:

    with get_db_session() as db:

        user = _find_user(db, user_id)

        if user is None:
            return None

        return _user_to_profile_dict(user)


# ==========================================
# UPDATE EDITABLE CONTACT DETAILS ONLY
# ==========================================

def update_profile(
    *,
    user_id: int,
    secondary_email: str,
    secondary_phone: str,
    emergency_contact_name: str,
    emergency_contact_phone: str,
    preferred_contact_method: str,
) -> dict:

    validate_profile_update(
        secondary_email=secondary_email,
        secondary_phone=secondary_phone,
        emergency_contact_name=emergency_contact_name,
        emergency_contact_phone=emergency_contact_phone,
        preferred_contact_method=preferred_contact_method,
    )

    cleaned_email = (
        secondary_email.strip().lower() or None
    )

    cleaned_phone = (
        secondary_phone.strip() or None
    )

    with get_db_session() as db:

        user = _find_user(db, user_id)

        if user is None:
            raise ValueError(
                "Resident account was not found."
            )

        # ----------------------------------
        # VALIDATE ADDITIONAL EMAIL
        # ----------------------------------

        if cleaned_email:

            if cleaned_email == user.email.strip().lower():
                raise ValueError(
                    "Additional email must differ "
                    "from primary email."
                )

            taken_primary = db.scalar(
                select(User.id).where(
                    func.lower(User.email) == cleaned_email
                )
            )

            if taken_primary is not None:
                raise ValueError(
                    "This additional email is already in use."
                )

            taken_secondary = db.scalar(
                select(ResidentProfile.user_id).where(
                    func.lower(
                        ResidentProfile.secondary_email
                    ) == cleaned_email,
                    ResidentProfile.user_id != user_id,
                )
            )

            if taken_secondary is not None:
                raise ValueError(
                    "This additional email is already in use."
                )

        # ----------------------------------
        # VALIDATE ADDITIONAL PHONE
        # ----------------------------------

        if cleaned_phone and user.phone:

            secondary_digits = re.sub(
                r"\D",
                "",
                cleaned_phone,
            )

            primary_digits = re.sub(
                r"\D",
                "",
                user.phone,
            )

            if secondary_digits == primary_digits:
                raise ValueError(
                    "Additional phone must differ "
                    "from primary phone."
                )

        # ----------------------------------
        # CREATE PROFILE IF MISSING
        # ----------------------------------

        if user.resident_profile is None:

            user.resident_profile = ResidentProfile(
                user_id=user.id
            )

            db.add(user.resident_profile)

        profile = user.resident_profile

        # ----------------------------------
        # UPDATE ONLY PERMITTED FIELDS
        # ----------------------------------

        profile.secondary_email = cleaned_email

        profile.secondary_phone = cleaned_phone

        profile.emergency_contact_name = (
            emergency_contact_name.strip() or None
        )

        profile.emergency_contact_phone = (
            emergency_contact_phone.strip() or None
        )

        profile.preferred_contact_method = (
            preferred_contact_method
        )

        # No changes are made to:
        # user.first_name
        # user.last_name
        # user.email
        # user.phone

        db.flush()

        return _user_to_profile_dict(user)
