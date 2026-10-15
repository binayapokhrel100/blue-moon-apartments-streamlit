
"""Blue Moon Apartments resident sidebar."""

import html

import streamlit as st

from core.session import get_current_user, logout_user
from services.notification_service import get_unread_count


# ==================================================
# RESIDENT NAVIGATION ITEMS
# ==================================================

NAVIGATION_ITEMS = [
    ("Dashboard", "dashboard", "dashboard"),
    ("Payments", "payments", "credit_card"),
    ("Maintenance", "maintenance", "build"),
    ("Announcements", "announcements", "campaign"),
    ("Community News", "community_news", "groups"),
    ("Notifications", "notifications", "notifications"),
    ("My Lease", "lease", "description"),
    ("Profile", "profile", "person"),
    ("Security", "security", "shield"),
]


# ==================================================
# NAVIGATION STATE
# ==================================================

def set_page(page_name: str) -> None:
    """Change the current resident page."""

    st.session_state.current_page = page_name


# ==================================================
# RESIDENT INITIALS
# ==================================================

def get_initials(name: str) -> str:
    """Return initials for the resident profile avatar."""

    return "".join(
        word[0]
        for word in name.split()
        if word
    )[:2].upper() or "R"


# ==================================================
# ACTIVE NAVIGATION STYLING
# ==================================================

def apply_active_style(
    current_page: str,
    unread_count: int,
) -> None:
    """Highlight selected navigation and notification count."""

    allowed = {
        page
        for _, page, _ in NAVIGATION_ITEMS
    }

    allowed.add("assistant")

    # ------------------------------------------
    # ACTIVE PAGE INDICATOR
    # ------------------------------------------

    if current_page in allowed:

        st.html(
            f"""
            <style>

            [data-testid="stSidebar"]
            .st-key-nav_{current_page} button {{
                background: #28364b !important;
                color: #ffffff !important;
                font-weight: 650 !important;
            }}

            [data-testid="stSidebar"]
            .st-key-nav_{current_page} button::before {{
                content: "";
                position: absolute;
                left: 0;
                top: 19%;
                height: 62%;
                width: 3px;
                border-radius: 4px;
                background: #2b8cff;
            }}

            </style>
            """
        )

    # ------------------------------------------
    # UNREAD NOTIFICATION BADGE
    # ------------------------------------------

    if unread_count > 0:

        badge = str(
            min(unread_count, 99)
        )

        if unread_count > 99:
            badge = "99+"

        st.html(
            f"""
            <style>

            [data-testid="stSidebar"]
            .st-key-nav_notifications button::after {{
                content: "{badge}";
                display: inline-flex;
                align-items: center;
                justify-content: center;
                margin-left: auto;
                background: #1766ad;
                color: white;
                border-radius: 999px;
                min-width: 18px;
                height: 18px;
                padding: 0 5px;
                font-size: 10px;
                font-weight: 700;
                flex-shrink: 0;
            }}

            </style>
            """
        )


# ==================================================
# NAVIGATION BUTTON
# ==================================================

def navigation_button(
    label: str,
    page: str,
    icon: str,
) -> None:
    """Render a left-aligned Material navigation button."""

    if st.button(
        label,
        icon=f":material/{icon}:",
        key=f"nav_{page}",
        use_container_width=True,
        type="tertiary",
    ):

        set_page(page)

        st.rerun()


# ==================================================
# RESIDENT SIDEBAR
# ==================================================

def render_sidebar() -> str:
    """Display Blue Moon sidebar and return selected page."""

    user = get_current_user() or {}

    # ------------------------------------------
    # RESIDENT INFORMATION
    # ------------------------------------------

    user_id = user.get("id")

    full_name = str(
        user.get("full_name")
        or "Resident"
    )

    apartment = str(
        user.get("apartment_unit")
        or "N/A"
    )

    # Escape values used in HTML.

    safe_name = html.escape(
        full_name
    )

    safe_apartment = html.escape(
        apartment
    )

    safe_initials = html.escape(
        get_initials(full_name)
    )

    # ------------------------------------------
    # UNREAD NOTIFICATION COUNT
    # ------------------------------------------

    unread_count = 0

    if user_id is not None:

        unread_count = max(
            0,
            int(
                get_unread_count(user_id)
                or 0
            ),
        )

    # ------------------------------------------
    # CURRENT PAGE
    # ------------------------------------------

    current_page = st.session_state.get(
        "current_page",
        "dashboard",
    )

    # ==================================================
    # SIDEBAR LAYOUT
    # ==================================================

    with st.sidebar:

        apply_active_style(
            current_page,
            unread_count,
        )

        with st.container(
            key="bm_sidebar_layout"
        ):

            # ==================================
            # BLUE MOON BRAND
            # ==================================

            st.html(
                '<div class="blue-moon-brand">'
                '<div class="moon-logo">&#9790;</div>'
                '<div class="brand-information">'
                '<div class="brand-title">'
                'Blue Moon'
                '</div>'
                '<div class="brand-subtitle">'
                'RESIDENT PORTAL'
                '</div>'
                '</div>'
                '</div>'
            )

            # ==================================
            # RESIDENT ACCOUNT BADGE
            # ==================================

            st.html(
                '<div class="account-badge-wrapper">'
                '<span class="account-badge">'
                'RESIDENT ACCOUNT'
                '</span>'
                '</div>'
            )

            # ==================================
            # NAVIGATION SECTION
            # ==================================

            st.html(
                '<div class="sidebar-section-title">'
                'NAVIGATION'
                '</div>'
            )

            for label, page, icon in NAVIGATION_ITEMS:

                navigation_button(
                    label=label,
                    page=page,
                    icon=icon,
                )

            # ==================================
            # ASSISTANT SECTION
            # ==================================

            st.html(
                '<div class="sidebar-section-title '
                'assistant-title">'
                'ASSISTANT'
                '</div>'
            )

            navigation_button(
                "Blue Moon Assistant",
                "assistant",
                "chat_bubble_outline",
            )

            # ==================================
            # RESIDENT FOOTER
            # ==================================

            with st.container(
                key="bm_sidebar_footer"
            ):

                # ------------------------------
                # RESIDENT PROFILE
                # ------------------------------

                st.html(
                    '<div class="resident-profile">'

                    '<div class="resident-avatar">'
                    f'{safe_initials}'
                    '</div>'

                    '<div class="resident-details">'

                    '<div class="resident-name">'
                    f'{safe_name}'
                    '</div>'

                    '<div class="resident-unit">'
                    f'Apt {safe_apartment}'
                    ' &middot; Resident'
                    '</div>'

                    '</div>'
                    '</div>'
                )

                # ------------------------------
                # FULL-WIDTH SIGN OUT BUTTON
                # ------------------------------

                if st.button(
                    "Sign Out",
                    icon=":material/logout:",
                    key="resident_signout_full",
                    use_container_width=True,
                    type="tertiary",
                ):

                    # Clear authenticated session.
                    logout_user()

                    # Return to portal selection.
                    st.session_state[
                        "bm_auth_screen"
                    ] = "selection"

                    st.rerun()

    # ------------------------------------------
    # RETURN SELECTED PAGE
    # ------------------------------------------

    return st.session_state.get(
        "current_page",
        "dashboard",
    )
