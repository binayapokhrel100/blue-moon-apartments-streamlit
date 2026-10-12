
import html
import re
from textwrap import dedent

import streamlit as st

from components.header import render_header
from services.announcement_service import (
    get_active_announcements,
)


# ==========================================
# ANNOUNCEMENT ICONS
# ==========================================

ANNOUNCEMENT_ICONS = {
    "General": "●",
    "Maintenance": "🔧",
    "Community": "⌂",
    "Safety": "◇",
    "Events": "☆",
    "Management": "▣",
}


# ==========================================
# HELPER FUNCTIONS
# ==========================================

def _safe_text(value) -> str:
    """
    Escape text before rendering it inside HTML.
    """
    if value is None:
        return ""

    return html.escape(
        str(value),
        quote=True,
    )


def _css_class(value: str) -> str:
    """
    Convert a category or priority into
    a safe CSS class suffix.
    """
    value = str(value).strip().lower()

    return re.sub(
        r"[^a-z0-9_-]+",
        "-",
        value,
    ).strip("-")


def _format_datetime(value) -> str:
    """
    Format announcement date and time.
    """
    if value is None:
        return "Not available"

    return value.strftime(
        "%b %d, %Y %I:%M %p"
    ).replace(
        " 0",
        " ",
    )


def _format_date(value) -> str:
    """
    Format expiration date.
    """
    if value is None:
        return "Not available"

    return value.strftime(
        "%b %d, %Y"
    ).replace(
        " 0",
        " ",
    )


# ==========================================
# ANNOUNCEMENT CARD
# ==========================================

def _render_announcement_card(
    announcement: dict,
) -> None:
    """
    Render a styled announcement card.

    Uses st.html() to prevent raw HTML
    from appearing in the Streamlit UI.
    """

    # --------------------------------------
    # Announcement details
    # --------------------------------------

    title = _safe_text(
        announcement.get("title", "")
    )

    message = _safe_text(
        announcement.get("message", "")
    )

    category_value = (
        announcement.get("category")
        or "General"
    )

    priority_value = (
        announcement.get("priority")
        or "Normal"
    )

    category = _safe_text(
        category_value
    )

    priority = _safe_text(
        priority_value
    )

    # --------------------------------------
    # Category icon
    # --------------------------------------

    icon = ANNOUNCEMENT_ICONS.get(
        category_value,
        "●",
    )

    # --------------------------------------
    # CSS class names
    # --------------------------------------

    category_class = _css_class(
        category_value
    )

    priority_class = _css_class(
        priority_value
    )

    # --------------------------------------
    # Publication date
    # --------------------------------------

    published = _safe_text(
        _format_datetime(
            announcement.get("published_at")
        )
    )

    # --------------------------------------
    # Expiration date
    # --------------------------------------

    expires_at = announcement.get(
        "expires_at"
    )

    if expires_at:

        expires_text = (
            "Visible through "
            + _format_date(expires_at)
        )

    else:

        expires_text = (
            "No expiration date"
        )

    expires_text = _safe_text(
        expires_text
    )

    # ======================================
    # RENDER ANNOUNCEMENT HTML
    # ======================================

    announcement_html = dedent(
        f"""
        <div class="announcement-card">

            <div class="announcement-icon announcement-{category_class}">
                {icon}
            </div>

            <div class="announcement-body">

                <div class="announcement-heading">

                    <div>

                        <span class="announcement-category">
                            {category}
                        </span>

                        <h3>
                            {title}
                        </h3>

                    </div>

                    <span class="announcement-priority priority-{priority_class}">
                        {priority}
                    </span>

                </div>

                <p class="announcement-message">
                    {message}
                </p>

                <div class="announcement-meta">

                    <span>
                        Published {published}
                    </span>

                    <span>
                        &nbsp; · &nbsp;
                    </span>

                    <span>
                        {expires_text}
                    </span>

                </div>

            </div>

        </div>
        """
    ).strip()

    # IMPORTANT:
    # st.html renders HTML directly.
    # It does not interpret the markup
    # as a Markdown code block.

    st.html(
        announcement_html
    )


# ==========================================
# MAIN ANNOUNCEMENTS PAGE
# ==========================================

def render_announcements() -> None:
    """
    Render the complete Announcements page
    for the Blue Moon Apartments portal.
    """

    # ======================================
    # PAGE HEADER
    # ======================================

    render_header(
        "Announcements"
    )

    header_html = dedent(
        """
        <h1 class="page-title">
            Announcements
        </h1>

        <p class="page-description">
            Important updates and notices
            from Blue Moon Apartments.
        </p>
        """
    ).strip()

    st.html(
        header_html
    )

    # ======================================
    # FETCH ACTIVE ANNOUNCEMENTS
    # ======================================

    announcements = (
        get_active_announcements()
    )

    # ======================================
    # EMPTY STATE
    # ======================================

    if not announcements:

        st.info(
            "There are currently "
            "no active announcements."
        )

        return

    # ======================================
    # DISPLAY ANNOUNCEMENTS
    # ======================================

    for announcement in announcements:

        _render_announcement_card(
            announcement
        )
