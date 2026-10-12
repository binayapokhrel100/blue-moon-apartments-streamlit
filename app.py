
"""Blue Moon Apartments resident portal."""

import streamlit as st

from components.sidebar import render_sidebar
from components.style_loader import load_css

from core.config import APP_NAME
from core.session import (
    initialize_session,
    is_authenticated,
)

from database.db import init_db

from views.announcements import render_announcements
from views.assistant import render_assistant
from views.community_news import render_community_news
from views.dashboard import render_dashboard
from views.lease import render_lease
from views.login import render_login
from views.maintenance import render_maintenance
from views.notifications import render_notifications
from views.payments import render_payments
from views.profile import render_profile
from views.security import render_security


# ==========================================
# STREAMLIT CONFIGURATION
# ==========================================

st.set_page_config(
    page_title=APP_NAME,
    page_icon="🌙",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ==========================================
# MAIN APPLICATION
# ==========================================

def main() -> None:

    # Initialize database and session.
    init_db()
    initialize_session()

    # Load global project styling.
    load_css()

    # ======================================
    # LOGIN
    # ======================================

    if not is_authenticated():

        render_login()
        return

    # ======================================
    # SIDEBAR NAVIGATION
    # ======================================

    current_page = render_sidebar()

    # ======================================
    # RESIDENT PAGES
    # ======================================

    if current_page == "dashboard":

        render_dashboard()

    elif current_page == "payments":

        render_payments()

    elif current_page == "maintenance":

        render_maintenance()

    elif current_page == "notifications":

        render_notifications()

    elif current_page == "announcements":

        render_announcements()

    elif current_page == "community_news":

        render_community_news()

    elif current_page == "lease":

        render_lease()

    elif current_page == "profile":

        render_profile()

    elif current_page == "security":

        render_security()

    # ======================================
    # BLUE MOON ASSISTANT — SPRINT 8
    # ======================================

    elif current_page == "assistant":

        render_assistant()

    # ======================================
    # FALLBACK
    # ======================================

    else:

        render_dashboard()


# ==========================================
# ENTRY POINT
# ==========================================

if __name__ == "__main__":
    main()
