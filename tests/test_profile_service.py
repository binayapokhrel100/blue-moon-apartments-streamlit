
"""Tests for Blue Moon Apartments resident profile validation."""

import inspect

import pytest

from services.profile_service import (
    update_profile,
    validate_profile_update,
)


# ==========================================
# VALID PROFILE DATA
# ==========================================

def valid_profile_data():
    return {
        "secondary_email": "sarah.backup@example.com",
        "secondary_phone": "214-555-0199",
        "emergency_contact_name": "Daniel Mitchell",
        "emergency_contact_phone": "214-555-0129",
        "preferred_contact_method": "Email",
    }


# ==========================================
# TEST 1: VALID PROFILE
# ==========================================

def test_valid_profile():

    data = valid_profile_data()

    validate_profile_update(**data)


# ==========================================
# TEST 2: INVALID SECONDARY EMAIL
# ==========================================

def test_invalid_email_rejected():

    data = valid_profile_data()

    data["secondary_email"] = "invalid-email"

    with pytest.raises(ValueError):
        validate_profile_update(**data)


# ==========================================
# TEST 3: INVALID SECONDARY PHONE
# ==========================================

def test_invalid_phone_rejected():

    data = valid_profile_data()

    data["secondary_phone"] = "123"

    with pytest.raises(ValueError):
        validate_profile_update(**data)


# ==========================================
# TEST 4: EMERGENCY NAME REQUIRES PHONE
# ==========================================

def test_emergency_name_requires_phone():

    data = valid_profile_data()

    data["emergency_contact_phone"] = ""

    with pytest.raises(ValueError):
        validate_profile_update(**data)


# ==========================================
# TEST 5: EMERGENCY PHONE REQUIRES NAME
# ==========================================

def test_emergency_phone_requires_name():

    data = valid_profile_data()

    data["emergency_contact_name"] = ""

    with pytest.raises(ValueError):
        validate_profile_update(**data)


# ==========================================
# TEST 6: INVALID EMERGENCY PHONE
# ==========================================

def test_invalid_emergency_phone_rejected():

    data = valid_profile_data()

    data["emergency_contact_phone"] = "12345"

    with pytest.raises(ValueError):
        validate_profile_update(**data)


# ==========================================
# TEST 7: INVALID CONTACT METHOD
# ==========================================

def test_invalid_contact_method():

    data = valid_profile_data()

    data["preferred_contact_method"] = (
        "Carrier Pigeon"
    )

    with pytest.raises(ValueError):
        validate_profile_update(**data)


# ==========================================
# TEST 8: OPTIONAL CONTACT DETAILS
# ==========================================

def test_optional_contacts_allowed():

    data = valid_profile_data()

    data["secondary_email"] = ""
    data["secondary_phone"] = ""

    validate_profile_update(**data)


# ==========================================
# TEST 9: SMS CONTACT METHOD
# ==========================================

def test_sms_contact_method():

    data = valid_profile_data()

    data["preferred_contact_method"] = "SMS"

    validate_profile_update(**data)


# ==========================================
# TEST 10: PHONE CONTACT METHOD
# ==========================================

def test_phone_contact_method():

    data = valid_profile_data()

    data["preferred_contact_method"] = "Phone"

    validate_profile_update(**data)


# ==========================================
# TEST 11: PRIMARY FIELDS NOT EDITABLE
# ==========================================

def test_primary_account_fields_not_editable():

    parameters = inspect.signature(
        update_profile
    ).parameters

    protected_fields = {
        "first_name",
        "last_name",
        "email",
        "phone",
    }

    for field in protected_fields:
        assert field not in parameters


# ==========================================
# TEST 12: ADDITIONAL EMAIL LENGTH
# ==========================================

def test_secondary_email_too_long():

    data = valid_profile_data()

    data["secondary_email"] = (
        "a" * 250 + "@example.com"
    )

    with pytest.raises(ValueError):
        validate_profile_update(**data)


# ==========================================
# TEST 13: BOTH EMERGENCY FIELDS EMPTY
# ==========================================

def test_emergency_contact_optional():

    data = valid_profile_data()

    data["emergency_contact_name"] = ""
    data["emergency_contact_phone"] = ""

    validate_profile_update(**data)
