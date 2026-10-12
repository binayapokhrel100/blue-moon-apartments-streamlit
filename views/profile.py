
"""Resident profile UI for Blue Moon Apartments."""

import html
from textwrap import dedent

import streamlit as st

from components.header import render_header
from core.session import get_current_user
from services.profile_service import (
    get_profile,
    update_profile,
)


CONTACT_METHODS = [
    "Email",
    "Phone",
    "SMS",
]


def _safe(value) -> str:
    """Escape text for safe HTML rendering."""
    return html.escape(
        str(value if value is not None else ""),
        quote=True,
    )


def render_profile() -> None:

    # ==========================================
    # CURRENT USER
    # ==========================================

    current_user = get_current_user() or {}
    user_id = current_user.get("id")

    if user_id is None:
        st.error(
            "Unable to identify the current resident."
        )
        return

    profile = get_profile(user_id)

    if profile is None:
        st.error(
            "Resident profile could not be loaded."
        )
        return

    # ==========================================
    # PAGE HEADER
    # ==========================================

    render_header("Profile")

    st.html(
        dedent(
            """
            <h1 class="page-title">Profile</h1>

            <p class="page-description">
                View your registered account details
                and manage additional contact information.
            </p>
            """
        ).strip()
    )

    # ==========================================
    # PROFILE SUMMARY
    # ==========================================

    full_name_value = (
        profile.get("full_name") or "Resident"
    )

    initials = "".join(
        name[0]
        for name in full_name_value.split()
        if name
    )[:2].upper() or "R"

    full_name = _safe(full_name_value)
    email = _safe(profile.get("email") or "")
    apartment = _safe(
        profile.get("apartment_unit") or "N/A"
    )

    st.html(
        dedent(
            f"""
            <div class="profile-summary-card">

                <div class="profile-large-avatar">
                    {_safe(initials)}
                </div>

                <div class="profile-summary-info">

                    <h3>{full_name}</h3>

                    <p>{email}</p>

                    <div class="profile-summary-meta">
                        <span>
                            Apartment {apartment}
                        </span>

                        <span>
                            Resident
                        </span>
                    </div>

                </div>

            </div>
            """
        ).strip()
    )

    # ==========================================
    # SUCCESS MESSAGE
    # ==========================================

    if "profile_success" in st.session_state:
        st.success(
            st.session_state.pop("profile_success")
        )

    # ==========================================
    # PRIMARY ACCOUNT INFORMATION
    # ==========================================

    st.html(
        """
        <div class="section-heading">
            <h3>Primary Account Information</h3>
            <p>
                These registered details cannot
                be changed here.
            </p>
        </div>
        """
    )

    left, right = st.columns(2)

    with left:

        st.text_input(
            "Full name",
            value=profile.get("full_name") or "",
            disabled=True,
            key="primary_full_name",
        )

        st.text_input(
            "Primary email",
            value=profile.get("email") or "",
            disabled=True,
            key="primary_email",
        )

    with right:

        st.text_input(
            "Apartment",
            value=(
                profile.get("apartment_unit") or "N/A"
            ),
            disabled=True,
            key="primary_apartment",
        )

        st.text_input(
            "Primary phone",
            value=profile.get("phone") or "",
            disabled=True,
            key="primary_phone",
        )

    st.caption(
        "Contact property management if your "
        "registered name, primary email, or "
        "primary phone number needs to change."
    )

    # ==========================================
    # ADDITIONAL CONTACT HEADING
    # ==========================================

    st.html(
        """
        <div class="section-heading">
            <h3>Additional Contact Information</h3>
            <p>
                Provide optional backup contact details.
            </p>
        </div>
        """
    )

    # ==========================================
    # EDITABLE PROFILE FORM
    # ==========================================

    with st.form(
        "resident_profile_form",
        clear_on_submit=False,
    ):

        left, right = st.columns(2)

        with left:

            secondary_email = st.text_input(
                "Additional email (optional)",
                value=(
                    profile.get("secondary_email")
                    or ""
                ),
                placeholder="alternate@example.com",
            )

        with right:

            secondary_phone = st.text_input(
                "Additional phone (optional)",
                value=(
                    profile.get("secondary_phone")
                    or ""
                ),
                placeholder="(214) 555-0100",
            )

        st.caption(
            "Additional contact details are not "
            "used for signing in or account recovery. "
            "Email verification is required before "
            "using an additional address for "
            "sensitive notifications."
        )

        # ======================================
        # EMERGENCY CONTACT
        # ======================================

        st.html(
            """
            <div class="profile-form-section">
                Emergency Contact
            </div>
            """
        )

        left, right = st.columns(2)

        with left:

            emergency_name = st.text_input(
                "Emergency contact name",
                value=(
                    profile.get(
                        "emergency_contact_name"
                    )
                    or ""
                ),
                placeholder="Full name",
            )

        with right:

            emergency_phone = st.text_input(
                "Emergency contact phone",
                value=(
                    profile.get(
                        "emergency_contact_phone"
                    )
                    or ""
                ),
                placeholder="(214) 555-0129",
            )

        # ======================================
        # COMMUNICATION PREFERENCES
        # ======================================

        st.html(
            """
            <div class="profile-form-section">
                Communication Preferences
            </div>
            """
        )

        saved_method = (
            profile.get("preferred_contact_method")
            or "Email"
        )

        method_index = (
            CONTACT_METHODS.index(saved_method)
            if saved_method in CONTACT_METHODS
            else 0
        )

        preferred_method = st.selectbox(
            "Preferred contact method",
            CONTACT_METHODS,
            index=method_index,
        )

        st.caption(
            "Your preference chooses a "
            "communication channel; it does not "
            "change primary contact details."
        )

        # ======================================
        # SAVE BUTTON
        # ======================================

        submitted = st.form_submit_button(
            "Save Contact Information",
            use_container_width=True,
        )

    # ==========================================
    # PROCESS FORM
    # ==========================================

    if submitted:

        try:

            update_profile(
                user_id=user_id,
                secondary_email=secondary_email,
                secondary_phone=secondary_phone,
                emergency_contact_name=emergency_name,
                emergency_contact_phone=emergency_phone,
                preferred_contact_method=preferred_method,
            )

        except ValueError as error:
            st.error(str(error))

        else:

            st.session_state[
                "profile_success"
            ] = (
                "Additional contact information "
                "updated successfully."
            )

            st.rerun()
