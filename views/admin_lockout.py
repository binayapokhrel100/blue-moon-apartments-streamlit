
"""Super Admin login recovery interface for Blue Moon Apartments."""

import streamlit as st

from services.admin_rbac_service import get_my_admin_access

from services.admin_lockout_service import (
    get_admin_login_lockout_status,
    unlock_admin_login,
)


def render_admin_lockout_recovery(
    *,
    admin_id: int,
    administrators: list[dict],
) -> None:
    """Render Super Admin-only administrator login recovery."""

    st.subheader("Administrator Login Recovery")

    st.caption(
        "Review temporary login restrictions and securely "
        "restore an employee's ability to sign in."
    )

    # --------------------------------------------------
    # VERIFY CURRENT ADMINISTRATOR ROLE
    # --------------------------------------------------

    try:
        access = get_my_admin_access(admin_id)
    except (PermissionError, ValueError):
        st.error("Administrator access is required.")
        return

    if access.get("role") != "super_admin":
        st.error("Only Super Admins can unlock administrator logins.")
        return

    # --------------------------------------------------
    # SHOW SUCCESSFUL UNLOCK NOTICE
    # --------------------------------------------------

    notice = st.session_state.pop(
        "bm_admin_unlock_success",
        None,
    )

    if notice:
        st.success(notice)

    # --------------------------------------------------
    # BUILD ADMINISTRATOR OPTIONS
    # --------------------------------------------------

    available = {}

    for item in administrators:

        if not isinstance(item, dict):
            continue

        user_id = item.get("user_id")

        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            continue

        # Self-unlock is prohibited.
        if user_id == admin_id:
            continue

        available[user_id] = item

    if not available:
        st.info("No other administrator accounts are available.")
        return

    def display_admin(user_id: int) -> str:

        item = available[user_id]

        name = (
            item.get("name")
            or item.get("full_name")
            or item.get("email")
            or f"Administrator #{user_id}"
        )

        employee_id = item.get("employee_id") or "N/A"

        return f"{name} — {employee_id}"

    # --------------------------------------------------
    # SELECT ADMINISTRATOR
    # --------------------------------------------------

    selected_id = st.selectbox(
        "Select administrator",
        options=sorted(available),
        format_func=display_admin,
        key="bm_unlock_target",
    )

    # --------------------------------------------------
    # FETCH LIVE LOCKOUT STATUS
    # --------------------------------------------------

    try:
        status = get_admin_login_lockout_status(
            actor_id=admin_id,
            target_admin_id=selected_id,
        )

    except (PermissionError, ValueError) as exc:
        st.error(str(exc))
        return

    # --------------------------------------------------
    # ACCOUNT INFORMATION
    # --------------------------------------------------

    st.markdown("#### Account Information")

    col1, col2 = st.columns(2)

    with col1:
        st.text_input(
            "Employee",
            value=status["name"],
            disabled=True,
        )

        st.text_input(
            "Employee ID",
            value=status["employee_id"],
            disabled=True,
        )

    with col2:
        st.text_input(
            "Email",
            value=status["email"],
            disabled=True,
        )

        st.text_input(
            "Assigned Role",
            value=status["role"].replace("_", " ").title(),
            disabled=True,
        )

    # --------------------------------------------------
    # LOGIN SECURITY STATUS
    # --------------------------------------------------

    st.markdown("#### Login Security Status")

    failures = status["failed_attempts"]
    maximum = status["max_attempts"]

    st.metric(
        "Recent Failed Login Attempts",
        f"{failures} / {maximum}",
    )

    st.caption(
        f"Authentication attempts are measured within "
        f"a rolling {status['window_minutes']}-minute window."
    )

    # --------------------------------------------------
    # PENDING PASSWORD RESET CHECK
    # --------------------------------------------------

    if status["pending_password_reset"]:

        st.warning(
            "This administrator has a pending password reset. "
            "The employee must complete the password reset "
            "workflow before ordinary login can resume."
        )

        return

    # --------------------------------------------------
    # ACTIVE LOCKOUT CHECK
    # --------------------------------------------------

    if not status["is_locked"]:

        st.success(
            "No active login lockout is detected for "
            "this administrator."
        )

        return

    st.warning(
        "This administrator is temporarily locked out "
        "because the failed login attempt limit was reached."
    )

    # --------------------------------------------------
    # SUPER ADMIN RECOVERY FORM
    # --------------------------------------------------

    st.markdown("#### Authorized Account Recovery")

    st.info(
        "Verify the employee's identity through an approved "
        "independent process before proceeding. "
        "Checking the box below does not itself verify identity."
    )

    with st.form("bm_admin_unlock_form"):

        reason = st.text_area(
            "Recovery reason",
            placeholder=(
                "Describe how the employee's identity "
                "was verified and why access is being restored."
            ),
            max_chars=500,
        )

        identity_verified = st.checkbox(
            "I confirm that I independently verified "
            "this employee's identity."
        )

        submitted = st.form_submit_button(
            "Unlock Administrator Login",
            type="primary",
            use_container_width=True,
        )

    # --------------------------------------------------
    # EXECUTE SECURE UNLOCK
    # --------------------------------------------------

    if submitted:

        try:

            result = unlock_admin_login(
                actor_id=admin_id,
                target_admin_id=selected_id,
                reason=reason,
                identity_verified=identity_verified,
            )

        except (PermissionError, ValueError) as exc:

            st.error(str(exc))
            return

        st.session_state["bm_admin_unlock_success"] = (
            "Administrator login successfully unlocked. "
            f"{result['cleared_failures']} failed attempts "
            "were cleared. The employee must still "
            "authenticate using valid credentials."
        )

        st.rerun()
