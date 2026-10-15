
"""Blue Moon Apartments — role-aware administrator sidebar."""

import html
from pathlib import Path

import streamlit as st

from core.admin_tenant_workflows import get_tenant_workflows
from core.session import get_current_user, logout_user

from services.admin_rbac_service import get_my_admin_access


# ==========================================================
# ADMINISTRATOR NAVIGATION ITEMS
# ==========================================================

MANAGEMENT_ITEMS = [
    ("Overview", "overview", "dashboard"),
    ("Tenant Management", "tenants", "groups"),
    ("Apartments", "apartments", "apartment"),
    ("Payments", "payments", "credit_card"),
    ("Maintenance", "maintenance", "build"),
    (
        "Administrator Management",
        "admin_users",
        "admin_panel_settings",
    ),
]


COMMUNICATION_ITEMS = [
    ("Announcements", "announcements", "campaign"),
    ("Community News", "community_news", "newspaper"),
]


# Personal account route for every valid administrator.
MY_ACCOUNT_PAGE = "my_account"


ADMIN_PAGES = {
    page
    for _, page, _ in (
        MANAGEMENT_ITEMS + COMMUNICATION_ITEMS
    )
} | {MY_ACCOUNT_PAGE}


# ==========================================================
# RBAC PERMISSION REQUIREMENTS
# ==========================================================

PAGE_REQUIREMENTS = {
    "overview": frozenset({
        "overview.read",
        "tenants.read",
        "apartments.read",
        "maintenance.read",
        "payments.read",
        "announcements.read",
    }),

    "tenants": frozenset({
        "admins.manage",
    }),

    "apartments": frozenset({
        "apartments.read",
    }),

    "payments": frozenset({
        "payments.read",
    }),

    "maintenance": frozenset({
        "maintenance.update",
    }),

    "announcements": frozenset({
        "announcements.manage",
    }),

    "community_news": frozenset({
        "news.manage",
    }),

    "admin_users": frozenset({
        "admins.manage",
    }),
}


# ==========================================================
# AUTHORIZED ADMINISTRATOR PAGES
# ==========================================================

def get_visible_admin_pages(
    access: dict,
) -> set[str]:
    """
    Return business pages authorized for this administrator.

    My Account is handled separately because it is a
    personal security page, not a business permission.
    """

    granted = set(
        access.get("permissions") or []
    )

    allowed = {
        page
        for page, requirements in PAGE_REQUIREMENTS.items()
        if requirements.issubset(granted)
    }

    # Tenant Management contains several independent
    # workflows with their own permissions.

    if get_tenant_workflows(granted):
        allowed.add("tenants")

    return allowed


# ==========================================================
# NAVIGATION STATE
# ==========================================================

def set_admin_page(
    page_name: str,
) -> None:
    """Set the current sidebar page."""

    if page_name in ADMIN_PAGES:
        st.session_state[
            "admin_current_page"
        ] = page_name


# ==========================================================
# AVATAR INITIALS
# ==========================================================

def get_initials(
    name: str,
) -> str:
    """Return up to two initials for the profile avatar."""

    return "".join(
        part[0]
        for part in name.split()
        if part
    )[:2].upper() or "A"


# ==========================================================
# LOAD EXTERNAL CSS
# ==========================================================

def load_admin_sidebar_css() -> None:
    """Load administrator sidebar CSS from the styles folder."""

    css_path = (
        Path(__file__).resolve().parent.parent
        / "styles"
        / "admin_sidebar.css"
    )

    if not css_path.is_file():

        st.error(
            "Missing stylesheet: "
            "styles/admin_sidebar.css"
        )

        return

    st.html(
        f"<style>"
        f"{css_path.read_text(encoding='utf-8')}"
        f"</style>"
    )


# ==========================================================
# SIDEBAR NAVIGATION BUTTON
# ==========================================================

def admin_navigation_button(
    label: str,
    page: str,
    icon: str,
    *,
    active: bool = False,
) -> None:
    """
    Render navigation buttons with consistent styling.

    The active page uses the primary button style.
    """

    if st.button(
        label,
        icon=f":material/{icon}:",
        key=f"nav_{page}",
        use_container_width=True,
        type=(
            "primary"
            if active
            else "tertiary"
        ),
    ):

        set_admin_page(page)

        st.rerun()


# ==========================================================
# RENDER ADMINISTRATOR SIDEBAR
# ==========================================================

def render_admin_sidebar(
    access: dict | None = None,
) -> str:
    """Render authorized navigation and My Account."""

    # ----------------------------------------------
    # CHECK AUTHENTICATED ADMINISTRATOR
    # ----------------------------------------------

    user = get_current_user() or {}

    if (
        str(user.get("role") or "")
        .strip()
        .lower() != "admin"
    ):

        st.error(
            "Administrator access required."
        )

        st.stop()

    admin_id = user.get("id")

    if not admin_id:

        st.error(
            "Your session is no longer valid."
        )

        st.stop()

    # ----------------------------------------------
    # FETCH CURRENT ROLE PERMISSIONS
    # ----------------------------------------------

    if access is None:

        try:

            access = get_my_admin_access(
                int(admin_id)
            )

        except (PermissionError, ValueError):

            st.error(
                "Administrator access could not "
                "be verified."
            )

            st.stop()

    allowed = get_visible_admin_pages(
        access
    )

    # ----------------------------------------------
    # DETERMINE CURRENT PAGE
    # ----------------------------------------------

    ordered_pages = [
        page
        for _, page, _ in (
            MANAGEMENT_ITEMS + COMMUNICATION_ITEMS
        )
        if page in allowed
    ]

    current_page = st.session_state.get(
        "admin_current_page",
        "overview",
    )

    # Keep My Account available to all authenticated
    # administrators with valid role access.

    if (
        current_page != MY_ACCOUNT_PAGE
        and current_page not in allowed
    ):

        current_page = (
            ordered_pages[0]
            if ordered_pages
            else ""
        )

        st.session_state[
            "admin_current_page"
        ] = current_page

    # ----------------------------------------------
    # ADMINISTRATOR PROFILE DETAILS
    # ----------------------------------------------

    full_name = str(
        user.get("full_name")
        or "Administrator"
    )

    email = str(
        user.get("email")
        or "Administrator"
    )

    safe_name = html.escape(
        full_name,
        quote=True,
    )

    safe_email = html.escape(
        email,
        quote=True,
    )

    safe_initials = html.escape(
        get_initials(full_name),
        quote=True,
    )

    role_label = html.escape(
        str(
            access.get("role_label")
            or "Unassigned"
        ),
        quote=True,
    )

    # ======================================================
    # BUILD SIDEBAR
    # ======================================================

    with st.sidebar:

        load_admin_sidebar_css()

        with st.container(
            key="bm_sidebar_layout"
        ):

            # ==================================
            # BLUE MOON BRAND
            # ==================================

            st.html(
                '<div class="blue-moon-brand">'
                '<div class="moon-logo">'
                '&#9790;'
                '</div>'
                '<div class="brand-information">'
                '<div class="brand-title">'
                'Blue Moon'
                '</div>'
                '<div class="brand-subtitle">'
                'MANAGEMENT PORTAL'
                '</div>'
                '</div>'
                '</div>'
            )

            # ==================================
            # ADMINISTRATOR ROLE BADGE
            # ==================================

            st.html(
                '<div class="account-badge-wrapper">'
                '<span class="account-badge">'
                f'{role_label}'
                '</span>'
                '</div>'
            )

            # ==================================
            # MANAGEMENT NAVIGATION
            # ==================================

            management = [
                item
                for item in MANAGEMENT_ITEMS
                if item[1] in allowed
            ]

            if management:

                st.html(
                    '<div class="sidebar-section-title">'
                    'MANAGEMENT'
                    '</div>'
                )

                for label, page, icon in management:

                    admin_navigation_button(
                        label,
                        page,
                        icon,
                        active=(
                            page == current_page
                        ),
                    )

            # ==================================
            # COMMUNICATION NAVIGATION
            # ==================================

            communication = [
                item
                for item in COMMUNICATION_ITEMS
                if item[1] in allowed
            ]

            if communication:

                st.html(
                    '<div class="sidebar-section-title '
                    'assistant-title">'
                    'COMMUNICATION'
                    '</div>'
                )

                for label, page, icon in communication:

                    admin_navigation_button(
                        label,
                        page,
                        icon,
                        active=(
                            page == current_page
                        ),
                    )

            # ==================================
            # MY ACCOUNT NAVIGATION
            # ==================================

            st.html(
                '<div class="sidebar-section-title '
                'assistant-title">'
                'ACCOUNT'
                '</div>'
            )

            admin_navigation_button(
                "My Account",
                MY_ACCOUNT_PAGE,
                "manage_accounts",
                active=(
                    current_page == MY_ACCOUNT_PAGE
                ),
            )

            # ==================================
            # EXISTING PROFILE AND SIGN OUT
            # ==================================

            with st.container(
                key="bm_sidebar_footer"
            ):

                # Original static circular avatar.
                # No clickable popover or extra password
                # control is rendered here.

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
                    f'{safe_email}'
                    '</div>'
                    '</div>'
                    '</div>'
                )

                # Existing Sign Out button.

                if st.button(
                    "Sign Out",
                    icon=":material/logout:",
                    key="admin_signout_full",
                    use_container_width=True,
                    type="tertiary",
                ):

                    logout_user()

                    st.session_state.pop(
                        "admin_current_page",
                        None,
                    )

                    st.session_state[
                        "bm_auth_screen"
                    ] = "selection"

                    st.rerun()

    return current_page
