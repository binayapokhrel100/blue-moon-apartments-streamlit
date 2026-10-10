
"""Blue Moon Apartments resident sidebar."""

import html

import streamlit as st

from core.session import get_current_user, logout_user
from services.notification_service import get_unread_count


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


def set_page(page_name: str) -> None:
    st.session_state.current_page = page_name


def get_initials(name: str) -> str:
    return "".join(
        word[0] for word in name.split() if word
    )[:2].upper() or "R"


def apply_active_style(
    current_page: str,
    unread_count: int,
) -> None:
    """Highlight selected navigation and notification count."""

    allowed = {page for _, page, _ in NAVIGATION_ITEMS}
    allowed.add("assistant")

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

    if unread_count > 0:
        badge = str(min(unread_count, 99))
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


def navigation_button(
    label: str,
    page: str,
    icon: str,
) -> None:
    if st.button(
        label,
        icon=f":material/{icon}:",
        key=f"nav_{page}",
        use_container_width=True,
        type="tertiary",
    ):
        set_page(page)
        st.rerun()


def render_sidebar() -> str:
    """Display Blue Moon sidebar and return selected page."""

    user = get_current_user() or {}

    user_id = user.get("id")
    full_name = str(user.get("full_name") or "Resident")
    apartment = str(user.get("apartment_unit") or "N/A")

    safe_name = html.escape(full_name)
    safe_apartment = html.escape(apartment)
    safe_initials = html.escape(get_initials(full_name))

    unread_count = 0

    if user_id is not None:
        unread_count = max(
            0,
            int(get_unread_count(user_id) or 0),
        )

    current_page = st.session_state.get(
        "current_page",
        "dashboard",
    )

    with st.sidebar:
        apply_active_style(current_page, unread_count)

        with st.container(key="bm_sidebar_layout"):

            # BRAND
            st.html(
                '<div class="blue-moon-brand">'
                '<div class="moon-logo">&#9790;</div>'
                '<div class="brand-information">'
                '<div class="brand-title">Blue Moon</div>'
                '<div class="brand-subtitle">RESIDENT PORTAL</div>'
                '</div></div>'
            )

            # ACCOUNT
            st.html(
                '<div class="account-badge-wrapper">'
                '<span class="account-badge">'
                'RESIDENT ACCOUNT'
                '</span></div>'
            )

            # NAVIGATION
            st.html(
                '<div class="sidebar-section-title">'
                'NAVIGATION'
                '</div>'
            )

            for label, page, icon in NAVIGATION_ITEMS:
                navigation_button(label, page, icon)

            # ASSISTANT
            st.html(
                '<div class="sidebar-section-title assistant-title">'
                'ASSISTANT'
                '</div>'
            )

            navigation_button(
                "Blue Moon Assistant",
                "assistant",
                "chat_bubble_outline",
            )

            # FOOTER
            with st.container(key="bm_sidebar_footer"):

                profile_col, logout_col = st.columns(
                    [5, 1],
                    gap="small",
                    vertical_alignment="center",
                )

                with profile_col:
                    st.html(
                        '<div class="resident-profile">'
                        f'<div class="resident-avatar">{safe_initials}</div>'
                        '<div class="resident-details">'
                        f'<div class="resident-name">{safe_name}</div>'
                        f'<div class="resident-unit">Apt {safe_apartment} &middot; Resident</div>'
                        '</div></div>'
                    )

                with logout_col:
                    if st.button(
                        "Sign Out",
                        icon=":material/logout:",
                        key="logout_button",
                        help="Sign Out",
                        type="tertiary",
                    ):
                        logout_user()
                        st.rerun()

    return st.session_state.get(
        "current_page",
        "dashboard",
    )
