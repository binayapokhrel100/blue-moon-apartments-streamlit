from views.notifications import (
    render_notifications,
)

from views.maintenance import (
    render_maintenance,
)

from views.payments import (
    render_payments,
)
import streamlit as st

from components.sidebar import render_sidebar
from components.style_loader import load_css
from core.config import APP_NAME
from core.session import (
    initialize_session,
    is_authenticated,
)
from database.db import init_db
from views.dashboard import render_dashboard
from views.login import render_login
from views.placeholder import render_placeholder


st.set_page_config(
    page_title=APP_NAME,
    page_icon="🌙",
    layout="wide",
    initial_sidebar_state="expanded",
)


PAGE_TITLES = {
    "announcements": "Announcements",
    "community_news": "Community News",
    "lease": "My Lease",
    "profile": "Profile",
    "security": "Security",
    "assistant": "Blue Moon Assistant",
}


def main():

    init_db()

    initialize_session()

    load_css()

    if not is_authenticated():

        render_login()

        return

    current_page = render_sidebar()

    if current_page == "dashboard":

        render_dashboard()
    elif current_page == "payments":

        render_payments()
    elif current_page == "maintenance":
        render_maintenance()

    elif current_page == "notifications":

        render_notifications()

    elif current_page in PAGE_TITLES:

        render_placeholder(
            PAGE_TITLES[current_page]
        )

    else:

        render_dashboard()


if __name__ == "__main__":
    main()