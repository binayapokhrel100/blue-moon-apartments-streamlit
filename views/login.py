
"""Blue Moon Apartments — resident and admin login experience."""

import logging
from pathlib import Path
from views.admin_password import render_admin_reset_code_page
from textwrap import dedent

import streamlit as st

from core.client_info import get_client_info
from core.session import login_user
from services.auth_service import (
    authenticate_admin,
    authenticate_user,
)
from services.security_service import record_successful_login


logger = logging.getLogger(__name__)

AUTH_SCREENS = {
    "selection",
    "resident",
    "admin",
    "admin_reset",
}


# ==================================================
# HTML RENDERING HELPER
# ==================================================

def _html(markup: str) -> None:
    """Render HTML without indentation problems."""

    st.html(
        dedent(markup).strip()
    )


# ==================================================
# LOAD LOGIN STYLESHEET
# ==================================================

def _load_login_css() -> None:
    """Load styles/login.css."""

    css_path = (
        Path(__file__).resolve().parent.parent
        / "styles"
        / "login.css"
    )

    if not css_path.is_file():
        st.error(
            "Login stylesheet missing: "
            "styles/login.css"
        )
        return

    css = css_path.read_text(
        encoding="utf-8"
    )

    st.html(
        f"<style>{css}</style>"
    )


# ==================================================
# LOGIN SCREEN NAVIGATION
# ==================================================

def _show(screen: str) -> None:
    """Navigate between login screens."""

    if screen not in AUTH_SCREENS:
        return

    st.session_state[
        "bm_auth_screen"
    ] = screen

    st.rerun()


# ==================================================
# BLUE MOON BRAND
# ==================================================

def _brand(
    subtitle: str = "RESIDENT PORTAL",
) -> None:

    _html(
        f"""
        <div class="bm-auth-brand">

            <span
                class="bm-auth-mark"
                aria-hidden="true"
            >
                ☾
            </span>

            <div>
                <strong>
                    Blue Moon
                </strong>

                <small>
                    {subtitle}
                </small>
            </div>

        </div>
        """
    )


# ==================================================
# EXISTING RESIDENT AUTHENTICATION
# ==================================================

def _process_login(
    email: str,
    password: str,
) -> None:

    normalized_email = (
        email.strip().lower()
    )

    if not normalized_email:
        st.error(
            "Please enter your email address."
        )
        return

    if not password:
        st.error(
            "Please enter your password."
        )
        return

    # Authenticate using existing backend.

    user = authenticate_user(
        normalized_email,
        password,
    )

    # Resident login must not grant
    # access to non-resident accounts.

    if (
        user is None
        or str(
            getattr(user, "role", "")
        ).lower() != "resident"
    ):
        st.error(
            "Invalid email or password."
        )
        return

    # Record successful login activity.

    try:
        record_successful_login(
            user_id=user.id,
            client_info=get_client_info(),
        )

    except Exception:
        logger.exception(
            "Unable to record login security event."
        )

    # Establish the existing session.

    login_user(user)

    st.rerun()


# ==================================================
# SCREEN 1 — PORTAL SELECTION
# ==================================================

def _portal_selection() -> None:

    with st.container(
        key="bm_auth_frame"
    ):

        left, right = st.columns(
            [1.72, 1],
            gap=None,
        )

        # ----------------------------------
        # LEFT — APARTMENT HERO
        # ----------------------------------

        with left:

            with st.container(
                key="bm_auth_selection_visual"
            ):

                _brand()

                _html(
                    """
                    <div class="bm-auth-visual-copy">

                        <h1>
                            Your Home,
                            <br>
                            <em>
                                All in One Place.
                            </em>
                        </h1>

                        <p>
                            Manage your rent,
                            maintenance requests,
                            community updates,
                            and more.
                        </p>

                        <div class="bm-auth-pill-row">

                            <span>
                                Rent Payments
                            </span>

                            <span>
                                Maintenance
                            </span>

                            <span>
                                Community News
                            </span>

                            <span>
                                Secure Access
                            </span>

                        </div>

                        <div
                            class="bm-auth-carousel-dots"
                            aria-hidden="true"
                        >
                            <b></b>
                            <i></i>
                            <i></i>
                            <i></i>
                        </div>

                    </div>
                    """
                )

        # ----------------------------------
        # RIGHT — PORTAL CHOICE
        # ----------------------------------

        with right:

            with st.container(
                key="bm_auth_selection_panel"
            ):

                _html(
                    """
                    <div class="bm-auth-panel-intro">

                        <h2>
                            Sign in to your portal
                        </h2>

                        <p>
                            Choose your account
                            type to continue
                        </p>

                    </div>
                    """
                )

                # Resident login

                with st.container(
                    key="bm_auth_resident_choice"
                ):

                    if st.button(
                        "♙  Resident Login  ›",
                        key="bm_choose_resident",
                        use_container_width=True,
                    ):
                        _show("resident")

                    _html(
                        """
                        <p class="bm-auth-option-note">
                            Access your resident dashboard
                        </p>
                        """
                    )

                # Admin login

                with st.container(
                    key="bm_auth_admin_choice"
                ):

                    if st.button(
                        "♢  Admin Login  ›",
                        key="bm_choose_admin",
                        use_container_width=True,
                    ):
                        _show("admin")

                    _html(
                        """
                        <p class="bm-auth-option-note">
                            Management portal
                            (coming soon)
                        </p>
                        """
                    )

                _html(
                    """
                    <div class="bm-auth-divider">
                        New to Blue Moon?
                    </div>

                    <p class="bm-auth-center-note">
                        New tenant?
                        Create your resident account
                    </p>
                    """
                )

                if st.button(
                    "Activate Resident Account",
                    type="primary",
                    key="bm_activate_from_portal",
                    use_container_width=True,
                ):
                    st.info(
                        "Account activation is not "
                        "available yet. Please contact "
                        "your property office."
                    )

                _html(
                    """
                    <p class="bm-auth-legal">
                        Blue Moon Apartments
                        · Resident Portal
                    </p>
                    """
                )


# ==================================================
# SCREEN 2 — RESIDENT LOGIN
# ==================================================

def _resident_login() -> None:

    with st.container(
        key="bm_auth_frame"
    ):

        left, right = st.columns(
            [1.72, 1],
            gap=None,
        )

        # ----------------------------------
        # LEFT — BRAND AND FEATURES
        # ----------------------------------

        with left:

            with st.container(
                key="bm_auth_resident_visual"
            ):

                _brand("Resident Portal")

                _html(
                    """
                    <div class="bm-auth-resident-message">

                        <h1>
                            Your home,
                            <br>
                            at your fingertips.
                        </h1>

                        <p>
                            Pay rent, submit maintenance
                            requests, and stay informed
                            about your community —
                            all from one place.
                        </p>

                        <div class="bm-auth-feature-grid">

                            <span>
                                🏠 &nbsp; Rent Payments
                            </span>

                            <span>
                                🔧 &nbsp; Maintenance
                            </span>

                            <span>
                                📢 &nbsp; Announcements
                            </span>

                            <span>
                                ☾ &nbsp; Blue Moon Assistant
                            </span>

                        </div>

                    </div>
                    """
                )

        # ----------------------------------
        # RIGHT — RESIDENT FORM
        # ----------------------------------

        with right:

            with st.container(
                key="bm_auth_resident_panel"
            ):

                if st.button(
                    "←  Back",
                    key="bm_resident_back",
                ):
                    _show("selection")

                _html(
                    """
                    <div class="bm-auth-form-title">

                        <div class="bm-auth-form-eyebrow">
                            ♙ &nbsp; RESIDENT LOGIN
                        </div>

                        <h2>
                            Welcome back
                        </h2>

                        <p>
                            Sign in to your Blue Moon
                            resident account
                        </p>

                    </div>
                    """
                )

                # Existing authentication form

                with st.form(
                    "bm_resident_signin_form",
                    clear_on_submit=False,
                ):

                    email = st.text_input(
                        "Email Address *",
                        placeholder="name@example.com",
                        autocomplete="email",
                    )

                    password = st.text_input(
                        "Password *",
                        type="password",
                        placeholder="Enter your password",
                        autocomplete="current-password",
                    )

                    # Persistent sign-in requires
                    # a separate implementation.

                    st.checkbox(
                        "Remember me (coming soon)",
                        disabled=True,
                    )

                    submitted = (
                        st.form_submit_button(
                            "Sign In",
                            type="primary",
                            use_container_width=True,
                        )
                    )

                if submitted:
                    _process_login(
                        email,
                        password,
                    )

                if st.button(
                    "Forgot password?",
                    key="bm_resident_forgot",
                ):
                    st.info(
                        "Password recovery is not "
                        "available yet. Please contact "
                        "your property office."
                    )

                _html(
                    """
                    <div class="bm-auth-divider">
                        New resident?
                    </div>
                    """
                )

                if st.button(
                    "Activate your account",
                    key="bm_resident_activate",
                ):
                    st.info(
                        "Account activation is not "
                        "available yet. Contact "
                        "your property office."
                    )

                _html(
                    """
                    <div class="bm-auth-security-note">

                        <span aria-hidden="true">
                            ♢
                        </span>

                        Your account is protected by
                        password authentication.

                    </div>
                    """
                )

# ==================================================
# ADMIN LOGIN
# ==================================================

def _admin_login() -> None:
    """Render the functional administrator login form."""

    with st.container(
        key="bm_auth_admin_layout"
    ):

        _html(
            """
            <div class="bm-auth-admin-heading">

                <div class="bm-auth-admin-logo">
                    ☾
                </div>

                <h1>
                    Admin Portal
                </h1>

                <p>
                    Blue Moon Apartments
                    — Employee Access
                </p>

            </div>
            """
        )

        with st.container(
            key="bm_auth_admin_card"
        ):

            _html(
                """
                <div class="bm-auth-admin-notice">

                    <strong>
                        ♢ &nbsp; Restricted Access
                    </strong>

                    <small>
                        For authorized employees only
                    </small>

                </div>
                """
            )

            with st.form(
                "bm_admin_login_form",
                clear_on_submit=False,
            ):

                email = st.text_input(
                    "Company Email *",
                    placeholder="yourname@bluemoonapts.com",
                    autocomplete="email",
                )

                employee_id = st.text_input(
                    "Employee ID *",
                    placeholder="BM-EMP-XXXX",
                )

                password = st.text_input(
                    "Password *",
                    type="password",
                    placeholder="Enter your password",
                    autocomplete="current-password",
                )

                submitted = st.form_submit_button(
                    "Sign In to Admin Portal",
                    type="primary",
                    use_container_width=True,
                )

            if submitted:

                if not all([
                    email.strip(),
                    employee_id.strip(),
                    password,
                ]):
                    st.error(
                        "Please complete all required fields."
                    )

                else:

                    user = authenticate_admin(
                        email=email,
                        employee_id=employee_id,
                        password=password,
                    )

                    if user is None:
                        st.error(
                            "Invalid credentials or "
                            "unauthorized account."
                        )

                    else:

                        try:
                            record_successful_login(
                                user_id=user.id,
                                client_info=get_client_info(),
                            )
                        except Exception:
                            logger.exception(
                                "Unable to record admin login event."
                            )

                        login_user(user)

                        st.session_state.current_page = (
                            "admin_dashboard"
                        )

                        st.rerun()
        if st.session_state.pop(
            "bm_admin_password_reset_success",
            False,
            ):
            st.success(
                "Your password was reset successfully. "
                "Please sign in with your new password."
                )

        if st.button(
            "Have a One-Time Reset Code?",
            key="bm_admin_open_reset",
            use_container_width=True,
            ):
            _show("admin_reset")

        if st.button(
            "← Back to portal selection",
            key="bm_admin_back",
        ):
            _show("selection")


# ==================================================
# MAIN LOGIN ENTRY POINT
# ==================================================

def render_login() -> None:
    """
    Called by app.py whenever the user
    is not authenticated.
    """

    _load_login_css()

    screen = st.session_state.get(
        "bm_auth_screen",
        "selection",
    )

    if screen not in AUTH_SCREENS:
        screen = "selection"

    with st.container(
        key="bm_auth_root"
    ):

        if screen == "selection":
            _portal_selection()

        elif screen == "resident":
            _resident_login()
        elif screen == "admin":
            _admin_login()

        else:
            render_admin_reset_code_page()
