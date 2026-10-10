import streamlit as st

from database.models import User


def initialize_session() -> None:

    defaults = {
        "authenticated": False,
        "user": None,
        "current_page": "dashboard",
    }

    for key, value in defaults.items():

        if key not in st.session_state:
            st.session_state[key] = value


def login_user(user: User) -> None:

    apartment_unit = None

    if user.apartment:
        apartment_unit = user.apartment.unit_number

    st.session_state.authenticated = True

    st.session_state.user = {
        "id": user.id,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "full_name": user.full_name,
        "email": user.email,
        "role": user.role,
        "apartment_unit": apartment_unit,
    }

    st.session_state.current_page = "dashboard"


def logout_user() -> None:

    st.session_state.authenticated = False
    st.session_state.user = None
    st.session_state.current_page = "dashboard"


def is_authenticated() -> bool:

    return bool(
        st.session_state.get(
            "authenticated",
            False,
        )
    )


def get_current_user() -> dict | None:

    return st.session_state.get("user")