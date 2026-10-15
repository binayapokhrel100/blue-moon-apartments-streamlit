
"""Blue Moon Apartments — administrator password management."""

import streamlit as st

from core.session import (
    get_current_user,
    logout_user,
)
from services.admin_recovery_policy import (
    VERIFICATION_METHODS,
    DELIVERY_METHODS,
)
from services.admin_rbac_service import (
    change_own_admin_password,
    request_admin_password_reset,
    redeem_admin_password_reset,
    get_my_admin_access,
)


# ==========================================================
# SHARED PASSWORD CHANGE FORM
# ==========================================================

def _password_change_form(
    *,
    admin_id: int,
    form_key: str,
) -> None:
    """Render the secure administrator password-change form."""

    with st.form(
        form_key,
        clear_on_submit=False,
    ):

        current_password = st.text_input(
            "Current Password",
            type="password",
            autocomplete="current-password",
        )

        new_password = st.text_input(
            "New Password",
            type="password",
            autocomplete="new-password",
        )

        confirm_password = st.text_input(
            "Confirm New Password",
            type="password",
            autocomplete="new-password",
        )

        st.caption(
            "Your password must contain 12–72 UTF-8 "
            "bytes, an uppercase letter, a lowercase "
            "letter, a number, and a special character."
        )

        submitted = st.form_submit_button(
            "Change Password",
            type="primary",
            use_container_width=True,
        )

    if not submitted:
        return

    try:

        change_own_admin_password(
            admin_id,
            current_password=current_password,
            new_password=new_password,
            confirm_password=confirm_password,
        )

    except (PermissionError, ValueError) as exc:
        st.error(str(exc))
        return

    # Changing a password invalidates the old session.

    logout_user()

    st.session_state["bm_auth_screen"] = "admin"

    st.session_state[
        "bm_admin_password_changed_notice"
    ] = True

    st.rerun()


# ==========================================================
# REQUIRED FIRST-LOGIN PASSWORD CHANGE
# ==========================================================

def render_required_admin_password_change() -> None:
    """
    Require newly provisioned administrators to replace
    their initial passwords before accessing management.
    """

    session = get_current_user() or {}

    if (
        str(session.get("role") or "")
        .strip()
        .lower() != "admin"
    ):
        st.error(
            "Administrator authentication required."
        )
        st.stop()

    admin_id = int(session["id"])

    st.title(
        "Set Your Administrator Password"
    )

    st.warning(
        "Your account is using an initial administrator "
        "password. You must replace it before accessing "
        "the management portal."
    )

    st.info(
        "Choose a private password you have not used "
        "for other accounts. You will sign in again "
        "after changing it."
    )

    _password_change_form(
        admin_id=admin_id,
        form_key="bm_required_admin_password_form",
    )

    if st.button(
        "Sign Out",
        key="bm_required_password_signout",
    ):
        logout_user()
        st.session_state["bm_auth_screen"] = "selection"
        st.rerun()


# ==========================================================
# MY ACCOUNT PAGE
# ==========================================================

def render_admin_account_page() -> None:
    """
    Display the authenticated administrator's account
    details and password-change form.
    """

    session = get_current_user() or {}

    if (
        str(session.get("role") or "")
        .strip()
        .lower() != "admin"
    ):
        st.error(
            "Administrator authentication required."
        )
        st.stop()

    admin_id = int(session["id"])

    try:
        access = get_my_admin_access(admin_id)

    except (PermissionError, ValueError) as exc:
        st.error(str(exc))
        st.stop()

    st.title("My Account")

    st.caption(
        "View your administrator profile "
        "and manage your account security."
    )

    # --------------------------------------------------
    # ACCOUNT INFORMATION
    # --------------------------------------------------

    with st.container(border=True):

        st.subheader("Account Information")

        left, right = st.columns(2)

        with left:

            st.markdown("**Full Name**")

            st.write(
                session.get(
                    "full_name",
                    "Administrator",
                )
            )

            st.markdown("**Work Email**")

            st.write(
                session.get(
                    "email",
                    "",
                )
            )

        with right:

            st.markdown("**Employee ID**")

            st.write(
                access.get(
                    "employee_id",
                    "—",
                )
            )

            st.markdown("**Administrator Role**")

            st.write(
                access.get(
                    "role_label",
                    "Unassigned",
                )
            )

    st.divider()

    # --------------------------------------------------
    # PASSWORD CHANGE
    # --------------------------------------------------

    st.subheader("Change Password")

    st.caption(
        "Enter your current password and choose "
        "a new secure password. After changing it, "
        "you will need to sign in again."
    )

    _password_change_form(
        admin_id=admin_id,
        form_key="bm_admin_account_change_password_form",
    )


# ==========================================================
# SUPER ADMIN — SECURE PASSWORD RESET ISSUANCE
# ==========================================================

def render_super_admin_password_reset(
    admin_id: int,
    administrators: list[dict],
) -> None:
    """
    Allow Super Admin to issue a one-time reset code
    after documented independent identity verification.
    """

    try:
        access = get_my_admin_access(admin_id)

    except (PermissionError, ValueError) as exc:
        st.error(str(exc))
        return

    if access.get("role") != "super_admin":
        st.error("Super Admin access required.")
        return

    st.subheader(
        "Reset Administrator Password"
    )

    st.caption(
        "Issue a one-time recovery code after verifying "
        "the employee's identity through an approved "
        "independent process."
    )

    st.warning(
        "Issuing a reset revokes existing sessions and "
        "blocks ordinary password login until the "
        "employee redeems the code."
    )

    # --------------------------------------------------
    # SELECT ELIGIBLE ADMINISTRATORS
    # --------------------------------------------------

    candidates = [
        item
        for item in administrators
        if item.get("active")
        and item.get("role")
        and item.get("user_id") != admin_id
    ]

    if not candidates:
        st.info(
            "There are no other active administrators "
            "eligible for password reset."
        )
        return

    by_id = {
        int(item["user_id"]): item
        for item in candidates
    }

    # --------------------------------------------------
    # RESET REQUEST FORM
    # --------------------------------------------------

    with st.form(
        "bm_admin_issue_password_reset_form"
    ):

        target_id = st.selectbox(
            "Select Administrator",
            options=list(by_id),
            format_func=lambda value: (
                f"{by_id[value]['name']} "
                f"({by_id[value]['email']})"
            ),
        )

        selected = by_id[target_id]

        st.caption(
            f"Employee ID: {selected['employee_id']} "
            f"· Role: {selected['role_label']}"
        )

        st.markdown(
            "#### Identity Verification"
        )

        verification_method = st.selectbox(
            "Verification method *",
            options=list(VERIFICATION_METHODS),
            format_func=lambda value: (
                VERIFICATION_METHODS[value]
            ),
            help=(
                "Use a previously established, trusted "
                "verification process. Do not rely solely "
                "on contact information provided during "
                "the recovery request."
            ),
        )

        delivery_method = st.selectbox(
            "Recovery code delivery method *",
            options=list(DELIVERY_METHODS),
            format_func=lambda value: (
                DELIVERY_METHODS[value]
            ),
        )

        reason = st.text_area(
            "Reason and verification notes *",
            max_chars=300,
            placeholder=(
                "Explain why recovery is needed and how "
                "the employee's identity was verified. "
                "Never include passwords, recovery codes, "
                "or private verification answers."
            ),
        )

        identity_verified = st.checkbox(
            "I confirm that I independently verified "
            "this employee's identity using the selected "
            "method and will use the approved delivery method."
        )

        submitted = st.form_submit_button(
            "Issue One-Time Reset Code",
            type="primary",
            use_container_width=True,
        )

    if not submitted:
        return

    # --------------------------------------------------
    # ISSUE RESET CODE
    # --------------------------------------------------

    try:

        reset_code = request_admin_password_reset(
            actor_id=admin_id,
            target_admin_id=int(target_id),
            reason=reason,
            identity_verified=identity_verified,
            verification_method=verification_method,
            delivery_method=delivery_method,
        )

    except (PermissionError, ValueError) as exc:
        st.error(str(exc))
        return

    # --------------------------------------------------
    # DISPLAY CODE ON ISSUANCE ONLY
    # --------------------------------------------------

    st.success(
        "One-time reset code issued successfully. "
        "Copy it now; it cannot be retrieved again."
    )

    # Do not store the plaintext code in session_state,
    # database audit history, or application logs.

    st.code(
        reset_code,
        language=None,
    )

    st.warning(
        "This code expires in 15 minutes. "
        "Deliver it only through the verified method "
        "selected above. Do not send it in ordinary "
        "email, public chat, logs, or screenshots. "
        "The employee must choose their own new password."
    )


# ==========================================================
# UNAUTHENTICATED RESET CODE REDEMPTION
# ==========================================================

def render_admin_reset_code_page() -> None:
    """Allow administrators to redeem a one-time reset code."""

    st.title(
        "Administrator Password Reset"
    )

    st.caption(
        "Use the one-time reset code issued by your "
        "Super Admin to set a new password."
    )

    with st.form(
        "bm_admin_redeem_reset_form",
        clear_on_submit=False,
    ):

        email = st.text_input(
            "Work Email *",
            autocomplete="email",
        )

        employee_id = st.text_input(
            "Employee ID *",
        )

        reset_code = st.text_input(
            "One-Time Reset Code *",
            type="password",
        )

        new_password = st.text_input(
            "New Password *",
            type="password",
            autocomplete="new-password",
        )

        confirm_password = st.text_input(
            "Confirm New Password *",
            type="password",
            autocomplete="new-password",
        )

        st.caption(
            "Use 12–72 UTF-8 bytes with uppercase, "
            "lowercase, a number, and a special character."
        )

        submitted = st.form_submit_button(
            "Reset Password",
            type="primary",
            use_container_width=True,
        )

    # --------------------------------------------------
    # PROCESS RESET
    # --------------------------------------------------

    if submitted:

        try:

            redeem_admin_password_reset(
                email=email,
                employee_id=employee_id,
                reset_code=reset_code,
                new_password=new_password,
                confirm_password=confirm_password,
            )

        except (ValueError, PermissionError) as exc:
            st.error(str(exc))

        else:

            st.session_state[
                "bm_admin_password_reset_success"
            ] = True

            st.session_state[
                "bm_auth_screen"
            ] = "admin"

            st.rerun()

    # --------------------------------------------------
    # RETURN TO LOGIN
    # --------------------------------------------------

    if st.button(
        "← Back to Administrator Login",
        key="bm_admin_reset_back",
    ):

        st.session_state[
            "bm_auth_screen"
        ] = "admin"

        st.rerun()
