import logging

import streamlit as st

from core.client_info import (
    get_client_info,
)
from core.session import login_user
from services.auth_service import (
    authenticate_user,
)
from services.security_service import (
    record_successful_login,
)


logger = logging.getLogger(
    __name__
)


def render_login() -> None:

    st.markdown(
        """
<div class="login-brand">
    <div class="login-moon">☾</div>
    <h1>Blue Moon</h1>
    <p>RESIDENT PORTAL</p>
</div>
        """,
        unsafe_allow_html=True,
    )

    left, center, right = (
        st.columns(
            [1.1, 1, 1.1]
        )
    )

    with center:

        st.markdown(
            """
<div class="login-heading">
    <h2>Welcome Back</h2>
    <p>
        Sign in to access your
        resident account.
    </p>
</div>
            """,
            unsafe_allow_html=True,
        )

        with st.form(
            "resident_login_form",
            clear_on_submit=False,
        ):

            email = st.text_input(
                "Email address",
                placeholder=(
                    "sarah.mitchell@bluemoon.demo"
                ),
            )

            password = st.text_input(
                "Password",
                type="password",
                placeholder=(
                    "Enter your password"
                ),
            )

            submitted = (
                st.form_submit_button(
                    "Sign In",
                    use_container_width=True,
                )
            )

        if submitted:

            if not email.strip():

                st.error(
                    "Please enter your "
                    "email address."
                )

                return

            if not password:

                st.error(
                    "Please enter "
                    "your password."
                )

                return

            user = authenticate_user(
                email,
                password,
            )

            if user is None:

                st.error(
                    "Invalid email "
                    "or password."
                )

                return

            # Security logging should not
            # prevent a successful login.
            try:

                record_successful_login(
                    user_id=user.id,
                    client_info=(
                        get_client_info()
                    ),
                )

            except Exception:

                logger.exception(
                    "Unable to record "
                    "login security event."
                )

            login_user(
                user
            )

            st.success(
                "Login successful."
            )

            st.rerun()

        st.markdown(
            """
<div class="login-help">
    <p>
        Demo resident account
    </p>

    <strong>
        Sarah Mitchell · Apartment 4B
    </strong>
</div>
            """,
            unsafe_allow_html=True,
        )