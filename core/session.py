
"""Blue Moon Apartments — database-verified login sessions."""

import logging

import streamlit as st

from database.models import User
from services.auth_service import get_user_by_id
from services.admin_rbac_service import get_my_admin_access


logger = logging.getLogger(__name__)


# ==================================================
# SESSION INITIALIZATION
# ==================================================

def initialize_session() -> None:
    """Initialize session state without overwriting an existing login."""

    defaults = {
        "authenticated": False,
        "user": None,
        "current_page": "dashboard",
    }

    for key, value in defaults.items():

        if key not in st.session_state:
            st.session_state[key] = value


# ==================================================
# SESSION USER SNAPSHOT
# ==================================================

def _user_snapshot(user: User) -> dict:
    """Build session display data from a verified database user."""

    apartment_unit = None

    if user.apartment:
        apartment_unit = user.apartment.unit_number

    return {
        "id": user.id,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "full_name": user.full_name,
        "email": user.email,
        "role": str(user.role or "").strip().lower(),
        "apartment_unit": apartment_unit,
    }


# ==================================================
# LOGIN
# ==================================================

def login_user(user: User) -> None:
    """Establish a database-verified Streamlit session."""

    snapshot = _user_snapshot(user)

    if snapshot["role"] == "admin":

        # Capture the credential version at login.
        # Future password changes invalidate this version.

        access = get_my_admin_access(
            int(user.id)
        )

        if (
            not access.get("role")
            or not access.get("permissions")
        ):
            raise PermissionError(
                "Administrator role access is unavailable."
            )

        snapshot["credential_version"] = int(
            access.get("credential_version", 0)
        )

    st.session_state.authenticated = True
    st.session_state.user = snapshot
    st.session_state.current_page = "dashboard"


# ==================================================
# LOGOUT
# ==================================================

def logout_user() -> None:
    """Clear authenticated identity and admin navigation state."""

    st.session_state.authenticated = False
    st.session_state.user = None
    st.session_state.current_page = "dashboard"

    st.session_state.pop(
        "admin_current_page",
        None,
    )


# ==================================================
# CURRENT DATABASE-VERIFIED USER
# ==================================================

def get_current_user() -> dict | None:
    """
    Validate the authenticated user against the database.

    Checks:
    - Existing user account
    - Active account status
    - Unchanged portal identity
    - Active administrator employee record
    - Valid assigned administrator role

    Administrative permission changes are obtained from
    the database, not from the cached session dictionary.
    """

    if not st.session_state.get(
        "authenticated",
        False,
    ):
        return None

    cached_user = st.session_state.get(
        "user"
    )

    if not isinstance(cached_user, dict):
        logout_user()
        return None

    try:

        # ------------------------------------------
        # VALIDATE USER IDENTIFIER
        # ------------------------------------------

        user_id = int(
            cached_user["id"]
        )

        if user_id <= 0:
            logout_user()
            return None

        # ------------------------------------------
        # LOOK UP CURRENT DATABASE ACCOUNT
        # ------------------------------------------

        user = get_user_by_id(
            user_id
        )

        if user is None or not user.is_active:
            logout_user()
            return None

        database_role = (
            str(user.role or "").strip().lower()
        )

        cached_role = (
            str(cached_user.get("role") or "")
            .strip()
            .lower()
        )

        # Do not silently switch someone between
        # resident and administrator portals.

        if database_role != cached_role:
            logout_user()
            return None

        # ------------------------------------------
        # ADMINISTRATOR REVALIDATION
        # ------------------------------------------

        if database_role == "admin":

            access = get_my_admin_access(
                user_id
            )
            # Reject a session established before the
            # most recent credential security change.

            cached_version = int(
                cached_user.get(
                    "credential_version",
                    0,
                )
            )

            current_version = int(
                access.get(
                    "credential_version",
                    0,
                )
            )

            if cached_version != current_version:
                logout_user()
                return None


            # An employee without an assigned,
            # recognized role has no admin session.

            if (
                not access.get("role")
                or not access.get("permissions")
            ):
                logout_user()
                return None

        elif database_role != "resident":

            # Reject unsupported or unknown user roles.

            logout_user()
            return None

        # ------------------------------------------
        # REFRESH NON-SECURITY DISPLAY INFORMATION
        # ------------------------------------------

        refreshed_user = _user_snapshot(
            user
        )
        if database_role == "admin":
            refreshed_user["credential_version"] = current_version

        st.session_state.user = refreshed_user

        return refreshed_user

    except (PermissionError, ValueError, TypeError, KeyError):

        # Covers revoked administrator access
        # and invalid cached session identifiers.

        logout_user()
        return None

    except Exception:

        # Database or other unexpected failures
        # must not leave an apparently valid session.

        logger.exception(
            "Unable to revalidate authenticated session."
        )

        logout_user()
        return None


# ==================================================
# AUTHENTICATION STATUS
# ==================================================

def is_authenticated() -> bool:
    """
    Return True only for a database-verified session.

    Revalidating here also protects callers that check
    authentication without calling get_current_user().
    """

    return get_current_user() is not None
