
"""Security page for Blue Moon Apartments resident portal."""

import html
from datetime import datetime
from textwrap import dedent

import streamlit as st

from components.cards import metric_card
from components.header import render_header
from core.client_info import get_client_info
from core.session import get_current_user
from services.security_service import (
    change_password,
    get_login_events,
    get_security_summary,
)


# ==================================================
# HELPER FUNCTIONS
# ==================================================

def _safe(value, fallback="") -> str:
    """
    Escape dynamic values before displaying
    them inside HTML.
    """
    if value is None or value == "":
        value = fallback

    return html.escape(
        str(value),
        quote=True,
    )


def _format_datetime(value) -> str:
    """
    Format timestamps for the security timeline.
    """
    if value is None:
        return "Not recorded"

    if isinstance(value, datetime):
        return value.strftime(
            "%b %d, %Y %I:%M %p"
        ).replace(" 0", " ")

    return str(value)


def _format_date(value) -> str:
    if value is None:
        return "Not recorded"

    if isinstance(value, datetime):
        return value.strftime(
            "%b %d, %Y"
        ).replace(" 0", " ")

    return str(value)


def _vertical_space(height=18) -> None:
    """
    Consistent spacing between page sections.
    """
    st.html(
        f'<div style="height:{int(height)}px;"></div>'
    )


# ==================================================
# CURRENT SESSION CARD
# ==================================================

def _render_current_session(client_info: dict) -> None:

    device = _safe(
        client_info.get("device_name"),
        "Unknown Device",
    )

    browser = _safe(
        client_info.get("browser_name"),
        "Unknown Browser",
    )

    ip_address = _safe(
        client_info.get("ip_address"),
        "Unavailable",
    )

    session_html = dedent(
        f"""
        <div class="security-session-card">

            <div class="security-icon">
                ◇
            </div>

            <div class="security-session-body">

                <span class="security-label">
                    CURRENT SESSION
                </span>

                <h3>
                    {device} · {browser}
                </h3>

                <p>
                    IP / Network: {ip_address}
                </p>

            </div>

            <span class="security-current-badge">
                Current
            </span>

        </div>
        """
    ).strip()

    st.html(session_html)


# ==================================================
# LOGIN EVENT CARD
# ==================================================

def _render_login_event(event: dict) -> None:

    event_type = event.get(
        "event_type",
        "login_success",
    )

    success = event.get("success", True)

    if event_type == "password_changed":

        title = "Password Changed"
        event_icon = "✓"

    elif success:

        title = "Successful Login"
        event_icon = "◇"

    else:

        title = "Unsuccessful Login"
        event_icon = "!"

    device_name = _safe(
        event.get("device_name"),
        "Unknown Device",
    )

    browser_name = _safe(
        event.get("browser_name"),
        "Unknown Browser",
    )

    event_ip = _safe(
        event.get("ip_address"),
        "Unavailable",
    )

    event_time = _safe(
        _format_datetime(
            event.get("created_at")
        )
    )

    if success:
        badge_text = "Successful"
        badge_class = "security-success-badge"
    else:
        badge_text = "Failed"
        badge_class = "security-failed-badge"

    event_html = dedent(
        f"""
        <div class="security-event-card">

            <div class="security-event-icon">
                {event_icon}
            </div>

            <div class="security-event-body">

                <h4>
                    {_safe(title)}
                </h4>

                <p>
                    {device_name} · {browser_name}
                </p>

                <span>
                    {event_time} · {event_ip}
                </span>

            </div>

            <span class="{badge_class}">
                {badge_text}
            </span>

        </div>
        """
    ).strip()

    st.html(event_html)


# ==================================================
# MAIN SECURITY PAGE
# ==================================================

def render_security() -> None:

    # ==========================================
    # CURRENT LOGGED-IN USER
    # ==========================================

    user = get_current_user() or {}

    user_id = user.get("id")

    if user_id is None:

        st.error(
            "Unable to identify the current resident."
        )

        return

    # ==========================================
    # LOAD SECURITY INFORMATION
    # ==========================================

    summary = (
        get_security_summary(user_id)
        or {}
    )

    client_info = (
        get_client_info()
        or {}
    )

    # ==========================================
    # PAGE HEADER
    # ==========================================

    render_header("Security")

    st.html(
        dedent(
            """
            <h1 class="page-title">
                Security
            </h1>

            <p class="page-description">
                Manage your password and review
                recent account activity.
            </p>
            """
        ).strip()
    )

    # ==========================================
    # SUCCESS NOTIFICATION
    # ==========================================

    if "security_success" in st.session_state:

        st.success(
            st.session_state.pop(
                "security_success"
            )
        )

    # ==========================================
    # SECURITY METRICS
    # ==========================================

    col1, col2, col3 = st.columns(3)

    with col1:

        metric_card(
            "Account Protection",
            "Protected",
            "Password enabled",
        )

    with col2:

        recent_login_count = (
            summary.get(
                "recent_login_count",
                0,
            )
        )

        metric_card(
            "Recent Logins",
            str(recent_login_count),
            "Recorded sessions",
        )

    with col3:

        last_change = (
            summary.get(
                "last_password_change"
            )
        )

        metric_card(
            "Password Changed",
            _format_date(last_change),
            "Security history",
        )

    _vertical_space(20)

    # ==========================================
    # CURRENT SESSION
    # ==========================================

    _render_current_session(
        client_info
    )

    _vertical_space(24)

    # ==========================================
    # RECENT LOGIN ACTIVITY
    # ==========================================

    st.html(
        dedent(
            """
            <div class="section-heading">

                <h3>
                    Recent Login Activity
                </h3>

                <p>
                    Review recent security events
                    associated with your account.
                </p>

            </div>
            """
        ).strip()
    )

    events = get_login_events(
        user_id=user_id,
        limit=10,
    )

    if not events:

        st.info(
            "No security activity has been recorded yet."
        )

    else:

        for event in events:

            _render_login_event(event)

    _vertical_space(24)

    # ==========================================
    # CHANGE PASSWORD HEADING
    # ==========================================

    st.html(
        dedent(
            """
            <div class="section-heading">

                <h3>
                    Change Password
                </h3>

                <p>
                    Use a strong password that
                    you do not use on other websites.
                </p>

            </div>
            """
        ).strip()
    )

    # ==========================================
    # CHANGE PASSWORD FORM
    # ==========================================

    with st.form(
        "change_password_form",
        clear_on_submit=True,
    ):

        current_password = st.text_input(
            "Current password",
            type="password",
            autocomplete="current-password",
        )

        password_col1, password_col2 = (
            st.columns(2)
        )

        with password_col1:

            new_password = st.text_input(
                "New password",
                type="password",
                autocomplete="new-password",
            )

        with password_col2:

            confirm_password = st.text_input(
                "Confirm new password",
                type="password",
                autocomplete="new-password",
            )

        st.caption(
            "Password must contain at least "
            "12 characters, including an "
            "uppercase letter, lowercase letter, "
            "number, and special character."
        )

        submitted = st.form_submit_button(
            "Change Password",
            use_container_width=True,
            type="primary",
        )

    # ==========================================
    # PROCESS PASSWORD CHANGE
    # ==========================================

    if submitted:

        if not current_password:

            st.error(
                "Please enter your current password."
            )

            return

        if not new_password:

            st.error(
                "Please enter a new password."
            )

            return

        if not confirm_password:

            st.error(
                "Please confirm your new password."
            )

            return

        try:

            change_password(
                user_id=user_id,
                current_password=current_password,
                new_password=new_password,
                confirm_password=confirm_password,
                client_info=client_info,
            )

            st.session_state[
                "security_success"
            ] = (
                "Your password was changed "
                "successfully."
            )

            st.rerun()

        except ValueError as error:

            st.error(
                str(error)
            )
