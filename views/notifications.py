
"""Resident notifications page."""

import html
from datetime import datetime

import streamlit as st

from components.header import render_header
from components.html_renderer import render_html
from core.session import get_current_user
from services.notification_service import (
    get_notifications_for_user,
    mark_all_notifications_read,
    mark_notification_read,
)


ICONS = {
    "payment": "▣",
    "maintenance": "⌕",
    "announcement": "♧",
    "security": "◇",
    "community": "☆",
    "general": "●",
}


def format_datetime(value) -> str:
    """Format a notification timestamp."""
    if not isinstance(value, datetime):
        return "Date unavailable"

    # Compatible with Windows and macOS.
    return value.strftime("%b %d, %Y %I:%M %p").replace(
        " 0", " "
    )


def render_notifications() -> None:
    """Render resident notifications."""

    user = get_current_user() or {}
    user_id = user.get("id")

    if user_id is None:
        st.error("Unable to identify the current resident.")
        return

    # ---------------------------------------------
    # HEADER
    # ---------------------------------------------

    render_header("Notifications")

    title_col, action_col = st.columns([5, 1])

    with title_col:
        render_html("""
        <h1 class="page-title">Notifications</h1>
        """)

    with action_col:
        if st.button(
            "Mark all read",
            key="mark_all_notifications",
            use_container_width=True,
        ):
            mark_all_notifications_read(user_id)
            st.rerun()

    # ---------------------------------------------
    # FETCH NOTIFICATIONS
    # ---------------------------------------------

    notifications = get_notifications_for_user(user_id)

    if not notifications:
        st.info("You do not have any notifications.")
        return

    # ---------------------------------------------
    # NOTIFICATION CARDS
    # ---------------------------------------------

    for notification in notifications:

        notification_type = str(
            notification.get(
                "notification_type",
                "general",
            )
        ).lower()

        # Limit dynamic CSS class names to known types.
        if notification_type not in ICONS:
            notification_type = "general"

        icon = ICONS[notification_type]

        title = html.escape(
            str(notification.get("title") or "")
        )

        message = html.escape(
            str(notification.get("message") or "")
        )

        is_read = bool(notification.get("is_read", False))
        is_alert = bool(notification.get("is_alert", False))

        unread_dot = (
            '<span class="unread-dot"></span>'
            if not is_read
            else ""
        )

        alert_badge = (
            '<span class="alert-badge">Alert</span>'
            if is_alert
            else ""
        )

        card_class = (
            "notification-card notification-alert"
            if is_alert
            else "notification-card"
        )

        date_text = html.escape(
            format_datetime(
                notification.get("created_at")
            )
        )

        render_html(f"""
        <div class="{card_class}">
            <div class="notification-icon notification-{notification_type}">
                {html.escape(icon)}
            </div>

            <div class="notification-content">
                <div class="notification-title">
                    {title}
                    {unread_dot}
                    {alert_badge}
                </div>

                <div class="notification-message">
                    {message}
                </div>

                <div class="notification-date">
                    {date_text}
                </div>
            </div>
        </div>
        """)

        # -----------------------------------------
        # MARK INDIVIDUAL NOTIFICATION AS READ
        # -----------------------------------------

        if not is_read:
            if st.button(
                "Mark as read",
                key=f"read_notification_{notification['id']}",
            ):
                mark_notification_read(
                    notification_id=notification["id"],
                    user_id=user_id,
                )

                st.rerun()
