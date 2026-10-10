
import html
from textwrap import dedent

import streamlit as st

from core.session import (
    get_current_user,
    logout_user,
)


NAVIGATION_ITEMS = {
    "Dashboard": "dashboard",
    "Payments": "payments",
    "Maintenance": "maintenance",
    "Announcements": "announcements",
    "Community News": "community_news",
    "Notifications": "notifications",
    "My Lease": "lease",
    "Profile": "profile",
    "Security": "security",
}


def _set_page(page_name: str) -> None:
    st.session_state.current_page = page_name


def render_html(markup: str) -> None:
    """Render HTML without Markdown indentation problems."""
    st.markdown(
        dedent(markup).strip(),
        unsafe_allow_html=True,
    )


def render_sidebar() -> str:
    user = get_current_user() or {}

    full_name = str(user.get("full_name") or "Resident")
    apartment = str(user.get("apartment_unit") or "N/A")

    initials = "".join(
        part[0]
        for part in full_name.split()
        if part
    )[:2].upper()

    # Escape user-controlled values before inserting into HTML.
    safe_name = html.escape(full_name)
    safe_apartment = html.escape(apartment)
    safe_initials = html.escape(initials)

    with st.sidebar:

        # ---------- BRAND ----------
        render_html("""
        <div class="blue-moon-brand">
            <div class="moon-logo">&#9790;</div>
            <div>
                <div class="brand-title">Blue Moon</div>
                <div class="brand-subtitle">RESIDENT PORTAL</div>
            </div>
        </div>
        """)

        # ---------- ACCOUNT BADGE ----------
        render_html("""
        <div class="account-badge">
            RESIDENT ACCOUNT
        </div>
        """)

        # ---------- NAVIGATION ----------
        render_html("""
        <div class="sidebar-section-title">
            NAVIGATION
        </div>
        """)

        for display_name, page_name in NAVIGATION_ITEMS.items():
            if st.button(
                display_name,
                key=f"nav_{page_name}",
                use_container_width=True,
            ):
                _set_page(page_name)
                st.rerun()

        # ---------- ASSISTANT ----------
        render_html("""
        <div class="sidebar-section-title">
            ASSISTANT
        </div>
        """)

        if st.button(
            "Blue Moon Assistant",
            key="nav_assistant",
            use_container_width=True,
        ):
            _set_page("assistant")
            st.rerun()

        st.markdown("---")

        # ---------- RESIDENT PROFILE ----------
        render_html(f"""
        <div class="resident-profile">
            <div class="resident-avatar">
                {safe_initials}
            </div>
            <div class="resident-details">
                <div class="resident-name">
                    {safe_name}
                </div>
                <div class="resident-unit">
                    Apt {safe_apartment} &middot; Resident
                </div>
            </div>
        </div>
        """)

        # ---------- LOGOUT ----------
        if st.button(
            "Sign Out",
            key="logout_button",
            use_container_width=True,
        ):
            logout_user()
            st.rerun()

    return st.session_state.current_page
