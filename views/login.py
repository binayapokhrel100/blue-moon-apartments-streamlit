
"""Blue Moon Apartments resident login page."""

import logging
from textwrap import dedent

import streamlit as st

from core.client_info import get_client_info
from core.session import login_user
from services.auth_service import authenticate_user
from services.security_service import record_successful_login


logger = logging.getLogger(__name__)


# ==================================================
# LOGIN BRAND
# ==================================================

def _render_login_brand() -> None:
    """Display the Blue Moon logo and branding."""

    st.html(
        dedent(
            """
            <div class="login-brand">

                <div class="login-moon">
                    ☾
                </div>

                <h1>
                    Blue Moon
                </h1>

                <p>
                    RESIDENT PORTAL
                </p>

            </div>
            """
        ).strip()
    )


# ==================================================
# WELCOME HEADING
# ==================================================

def _render_login_heading() -> None:
    """Display the login page welcome message."""

    st.html(
        dedent(
            """
            <div class="login-heading">

                <h2>
                    Welcome Back
                </h2>

                <p>
                    Sign in to access your
                    resident account.
                </p>

            </div>
            """
        ).strip()
    )


# ==================================================
# DEMO RESIDENT CARD
# ==================================================

def _render_demo_account() -> None:
    """Display the demo resident information."""

    st.html(
        dedent(
            """
            <div class="login-help">

                <p>
                    Demo resident account
                </p>

                <strong>
                    Sarah Mitchell · Apartment 4B
                </strong>

            </div>
            """
        ).strip()
    )


# ==================================================
# AUTHENTICATE RESIDENT
# ==================================================

def _process_login(
    email: str,
    password: str,
) -> None:
    """Validate credentials and create a user session."""

    cleaned_email = email.strip().lower()

    # ----------------------------------------------
    # INPUT VALIDATION
    # ----------------------------------------------

    if not cleaned_email:
        st.error(
            "Please enter your email address."
        )
        return

    if not password:
        st.error(
            "Please enter your password."
        )
        return

    # ----------------------------------------------
    # AUTHENTICATE USER
    # ----------------------------------------------

    user = authenticate_user(
        cleaned_email,
        password,
    )

    if user is None:
        st.error(
            "Invalid email or password."
        )
        return

    # ----------------------------------------------
    # RECORD SUCCESSFUL LOGIN
    # ----------------------------------------------

    try:
        record_successful_login(
            user_id=user.id,
            client_info=get_client_info(),
        )

    except Exception:
        # A logging failure should not block
        # an otherwise successful login.
        logger.exception(
            "Unable to record login security event."
        )

    # ----------------------------------------------
    # CREATE AUTHENTICATED SESSION
    # ----------------------------------------------

    login_user(user)

    # Refresh the app to display the
    # authenticated resident portal.
    st.rerun()


# ==================================================
# MAIN LOGIN PAGE
# ==================================================

def render_login() -> None:
    """Render the resident login page."""

    # ----------------------------------------------
    # CENTERED PAGE LAYOUT
    # ----------------------------------------------

    left, center, right = st.columns(
        [1, 1.4, 1],
        gap="medium",
    )

    with center:

        # ------------------------------------------
        # LOGO AND WELCOME HEADING
        # ------------------------------------------

        _render_login_brand()

        _render_login_heading()

        # ------------------------------------------
        # LOGIN FORM
        # ------------------------------------------

        with st.form(
            "resident_login_form",
            clear_on_submit=False,
        ):

            email = st.text_input(
                "Email address",
                placeholder=(
                    "sarah.mitchell@bluemoon.demo"
                ),
                autocomplete="email",
            )

            password = st.text_input(
                "Password",
                type="password",
                placeholder="Enter your password",
                autocomplete="current-password",
            )

            submitted = st.form_submit_button(
                "Sign In",
                use_container_width=True,
                type="primary",
            )

        # ------------------------------------------
        # HANDLE FORM SUBMISSION
        # ------------------------------------------

        if submitted:
            _process_login(
                email=email,
                password=password,
            )

        # ------------------------------------------
        # DEMO ACCOUNT INFORMATION
        # ------------------------------------------

        _render_demo_account()
