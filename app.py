import streamlit as st

from components.sidebar import render_sidebar
from components.style_loader import load_css
from core.config import APP_NAME
from views.dashboard import render_dashboard
from views.placeholder import render_placeholder


st.set_page_config(
    page_title=APP_NAME,
    page_icon="🌙",
    layout="wide",
    initial_sidebar_state="expanded",
)


PAGE_TITLES = {
    "payments": "Payments",
    "maintenance": "Maintenance",
    "announcements": "Announcements",
    "community_news": "Community News",
    "notifications": "Notifications",
    "lease": "My Lease",
    "profile": "Profile",
    "security": "Security",
    "assistant": "Blue Moon Assistant",
}


def main():

    load_css()

    current_page = render_sidebar()

    if current_page == "dashboard":
        render_dashboard()

    elif current_page in PAGE_TITLES:
        render_placeholder(
            PAGE_TITLES[current_page]
        )

    else:
        render_dashboard()


if __name__ == "__main__":
    main()