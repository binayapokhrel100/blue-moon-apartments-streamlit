
"""Blue Moon Apartments — resident and administrator portals."""

import streamlit as st

from core.config import APP_NAME

from core.session import (
    get_current_user,
    initialize_session,
    is_authenticated,
    logout_user,
)

from components.admin_sidebar import (
    get_visible_admin_pages,
    render_admin_sidebar,
)

from components.sidebar import render_sidebar
from components.style_loader import load_css

from database.db import init_db

from services.admin_rbac_service import get_my_admin_access
from services.auth_service import get_user_by_id


# ==================================================
# ADMINISTRATOR VIEWS
# ==================================================

from views.admin_apartments import render_admin_apartments
from views.admin_dashboard import render_admin_dashboard
from views.admin_maintenance import render_admin_maintenance
from views.admin_payments import render_admin_payments
from views.admin_tenants import render_admin_tenants
from views.admin_announcements import render_admin_announcements
from views.admin_community_news import render_admin_community_news
from views.admin_users import render_admin_users

from views.admin_password import (
    render_required_admin_password_change,
    render_admin_account_page,
)


# ==================================================
# RESIDENT VIEWS
# ==================================================

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


# ==================================================
# STREAMLIT CONFIGURATION
# ==================================================

st.set_page_config(
    page_title=APP_NAME,
    page_icon="\U0001F319",
#page_icon="🌙",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ==================================================
# VERIFY AUTHENTICATED USER ROLE
# ==================================================

def _verified_role() -> str | None:
    """Verify session identity using the current database."""

    session_user = get_current_user() or {}

    user_id = session_user.get(
        "id"
    )

    if not user_id:
        return None

    db_user = get_user_by_id(
        user_id
    )

    if (
        db_user is None
        or not db_user.is_active
    ):
        return None

    database_role = str(
        db_user.role or ""
    ).strip().lower()

    session_role = str(
        session_user.get("role") or ""
    ).strip().lower()

    if (
        database_role != session_role
        or database_role not in {
            "admin",
            "resident",
        }
    ):
        return None

    return database_role


# ==================================================
# RESIDENT PORTAL
# ==================================================

def _render_resident_portal() -> None:
    """Render the existing resident pages."""

    page = render_sidebar()

    routes = {
        "dashboard": render_dashboard,
        "payments": render_payments,
        "maintenance": render_maintenance,
        "notifications": render_notifications,
        "announcements": render_announcements,
        "community_news": render_community_news,
        "lease": render_lease,
        "profile": render_profile,
        "security": render_security,
        "assistant": render_assistant,
    }

    render_page = routes.get(
        page,
        render_dashboard,
    )

    render_page()


# ==================================================
# ROLE-AWARE ADMINISTRATOR PORTAL
# ==================================================

def _render_admin_portal() -> None:
    """Render only database-authorized admin pages."""

    session_user = get_current_user() or {}

    admin_id = session_user.get(
        "id"
    )

    if not admin_id:

        logout_user()

        st.error(
            "Please sign in again."
        )

        st.stop()

    # ----------------------------------------------
    # VERIFY CURRENT ADMINISTRATOR ACCESS
    # ----------------------------------------------

    try:

        access = get_my_admin_access(
            int(admin_id)
        )

    except (ValueError, PermissionError):

        logout_user()

        st.session_state.pop(
            "admin_current_page",
            None,
        )

        st.error(
            "Your administrator access is no longer valid. "
            "Please sign in again."
        )

        st.stop()

    # ----------------------------------------------
    # GET PERMITTED BUSINESS PAGES
    # ----------------------------------------------

    allowed_pages = get_visible_admin_pages(
        access
    )

    # ----------------------------------------------
    # RENDER ROLE-AWARE SIDEBAR
    # ----------------------------------------------

    page = render_admin_sidebar(
        access=access
    )

    # ==============================================
    # MY ACCOUNT — PERSONAL SECURITY PAGE
    # ==============================================

    # All administrators with valid role access can
    # manage their own account.
    # This route is intentionally separate from
    # permissions for resident or property operations.

    if page == "my_account":

        render_admin_account_page()

        return

    # ----------------------------------------------
    # NO AUTHORIZED BUSINESS PAGES
    # ----------------------------------------------

    if not allowed_pages:

        st.title(
            "Administrator Portal"
        )

        st.info(
            "Your administrator account is active, but "
            "no management pages are currently enabled "
            f"for the {access['role_label']} role."
        )

        return

    # ----------------------------------------------
    # BLOCK UNAUTHORIZED PAGE ACCESS
    # ----------------------------------------------

    if page not in allowed_pages:

        st.error(
            "You are not authorized to access this page."
        )

        return

    # ----------------------------------------------
    # ADMINISTRATOR PAGE ROUTES
    # ----------------------------------------------

    routes = {
        "overview": render_admin_dashboard,
        "tenants": render_admin_tenants,
        "apartments": render_admin_apartments,
        "payments": render_admin_payments,
        "maintenance": render_admin_maintenance,
        "announcements": render_admin_announcements,
        "community_news": render_admin_community_news,
        "admin_users": render_admin_users,
    }

    render_page = routes.get(
        page
    )

    if render_page is None:

        st.error(
            "The requested administrator page "
            "is unavailable."
        )

        return

    render_page()



@st.cache_resource(show_spinner=False)
def initialize_application_database():
    """Initialize or verify the database once per app process."""
    init_db()
    return True
# ==================================================
# MAIN APPLICATION
# ==================================================

def main() -> None:

    # ----------------------------------------------
    # INITIALIZE DATABASE AND SESSION
    # ----------------------------------------------

    initialize_application_database()

    initialize_session()

    load_css()

    # ----------------------------------------------
    # UNAUTHENTICATED USERS
    # ----------------------------------------------

    if not is_authenticated():

        if st.session_state.pop(
            "bm_admin_password_changed_notice",
            False,
        ):

            st.success(
                "Your administrator password was changed. "
                "Please sign in using your new password."
            )

        render_login()

        return

    # ----------------------------------------------
    # VERIFY LOGGED-IN ROLE
    # ----------------------------------------------

    role = _verified_role()

    if role is None:

        logout_user()

        st.session_state[
            "bm_auth_screen"
        ] = "selection"

        st.warning(
            "Your session is no longer valid. "
            "Please sign in again."
        )

        render_login()

        return

    # ==============================================
    # ADMINISTRATOR PORTAL
    # ==============================================

    if role == "admin":

        session_user = get_current_user() or {}

        try:

            access = get_my_admin_access(
                int(session_user["id"])
            )

        except (
            PermissionError,
            ValueError,
            KeyError,
            TypeError,
        ):

            logout_user()

            st.error(
                "Administrator access could not be verified."
            )

            st.stop()

        # ------------------------------------------
        # MANDATORY FIRST-LOGIN PASSWORD CHANGE
        # ------------------------------------------

        if access.get(
            "must_change_password"
        ):

            render_required_admin_password_change()

            return

        # ------------------------------------------
        # NORMAL ADMINISTRATOR PORTAL
        # ------------------------------------------

        _render_admin_portal()

    # ==============================================
    # RESIDENT PORTAL
    # ==============================================

    else:

        _render_resident_portal()


# ==================================================
# ENTRY POINT
# ==================================================

if __name__ == "__main__":
    main()
