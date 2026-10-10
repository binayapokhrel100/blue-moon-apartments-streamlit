import streamlit as st


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


def _set_page(page_name: str):
    st.session_state.current_page = page_name


def render_sidebar() -> str:
    if "current_page" not in st.session_state:
        st.session_state.current_page = "dashboard"

    with st.sidebar:

        st.markdown(
            """
            <div class="blue-moon-brand">
                <div class="moon-logo">☾</div>
                <div>
                    <div class="brand-title">Blue Moon</div>
                    <div class="brand-subtitle">RESIDENT PORTAL</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            '<div class="account-badge">RESIDENT ACCOUNT</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            '<div class="sidebar-section-title">NAVIGATION</div>',
            unsafe_allow_html=True,
        )

        for display_name, page_name in NAVIGATION_ITEMS.items():

            if st.button(
                display_name,
                key=f"nav_{page_name}",
                use_container_width=True,
            ):
                _set_page(page_name)

        st.markdown(
            '<div class="sidebar-section-title">ASSISTANT</div>',
            unsafe_allow_html=True,
        )

        if st.button(
            "Blue Moon Assistant",
            key="nav_assistant",
            use_container_width=True,
        ):
            _set_page("assistant")

        st.markdown("---")

        st.markdown(
            """
            <div class="resident-profile">
                <div class="resident-avatar">SM</div>

                <div class="resident-details">
                    <div class="resident-name">
                        Sarah Mitchell
                    </div>

                    <div class="resident-unit">
                        Apt 4B · Resident
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    return st.session_state.current_page