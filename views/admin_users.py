
"""Blue Moon Apartments — Super Admin employee and role management."""

from datetime import datetime

import streamlit as st

from views.admin_password import render_super_admin_password_reset
from views.admin_lockout import render_admin_lockout_recovery
from views.admin_security_monitoring import (
    render_admin_security_monitoring,
)

from core.admin_permissions import ROLES, ROLE_LABELS
from core.session import get_current_user

from services.admin_rbac_service import (
    assign_admin_role,
    set_admin_employee_active,
    create_admin_employee,
    get_my_admin_access,
    list_admin_role_assignments,
    list_admin_role_audit,
)


# ==================================================
# DATE / TIME DISPLAY HELPER
# ==================================================

def _timestamp(value) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value or "")


# ==================================================
# ADMINISTRATOR MANAGEMENT PAGE
# ==================================================

def render_admin_users() -> None:
    """Manage administrator employees through database-backed access."""

    session = get_current_user() or {}
    admin_id = session.get("id")

    if (
        str(session.get("role", "")).strip().lower() != "admin"
        or not admin_id
    ):
        st.error("Please sign in as an administrator.")
        st.stop()

    # ==================================================
    # VERIFY SUPER ADMIN
    # ==================================================

    try:
        admin_id = int(admin_id)

        access = get_my_admin_access(
            admin_id
        )

        if access.get("role") != "super_admin":
            raise PermissionError(
                "Only Super Admin may manage administrators."
            )

        administrators = list_admin_role_assignments(
            admin_id
        )

        audit_events = list_admin_role_audit(
            admin_id
        )

    except (PermissionError, ValueError) as exc:
        st.error(str(exc))
        st.stop()

    # ==================================================
    # PAGE HEADER
    # ==================================================

    st.title("Administrator Management")

    st.caption(
        "Create administrator employees, manage roles, "
        "and review audited changes. "
        "Employee accounts have separate login credentials."
    )

    flash = st.session_state.pop(
        "bm_admin_users_flash",
        None,
    )

    if flash:
        st.success(flash)

    # ==================================================
    # SUMMARY METRICS
    # ==================================================

    active_count = sum(
        bool(item["active"])
        for item in administrators
    )

    assigned_count = sum(
        bool(item["role"])
        for item in administrators
    )

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "Administrator Accounts",
        len(administrators),
    )

    c2.metric(
        "Active Administrators",
        active_count,
    )

    c3.metric(
        "Assigned Roles",
        assigned_count,
    )

    st.divider()

    # ==================================================
    # ADMINISTRATOR MANAGEMENT TABS
    # ==================================================

    (
        directory_tab,
        create_tab,
        assign_tab,
        audit_tab,
        status_tab,
        reset_tab,
        recovery_tab,
        security_tab,
    ) = st.tabs(
        [
            "Administrator Directory",
            "Create Administrator",
            "Assign / Change Role",
            "Role Audit History",
            "Account Status",
            "Password Reset",
            "Account Recovery",
            "Security Monitoring"
        ]
    )

    # ==================================================
    # TAB 1 — ADMINISTRATOR DIRECTORY
    # ==================================================

    with directory_tab:

        st.subheader("Administrator Directory")

        rows = [
            {
                "Employee ID": item["employee_id"],
                "Name": item["name"],
                "Email": item["email"],
                "Account Status": (
                    "Active" if item["active"] else "Inactive"
                ),
                "Assigned Role": item["role_label"],
            }
            for item in administrators
        ]

        if rows:
            st.dataframe(
                rows,
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.info(
                "No administrator employees found."
            )

    # ==================================================
    # TAB 2 — CREATE ADMINISTRATOR
    # ==================================================

    with create_tab:

        st.subheader("Create Administrator")

        st.caption(
            "Provision a separate administrator login "
            "and assign an initial role. Account creation "
            "is recorded in role audit history."
        )

        role_options = list(ROLES)

        role_default = (
            role_options.index("property_manager")
            if "property_manager" in role_options
            else 0
        )

        with st.form(
            "bm_create_admin_employee_form",
            clear_on_submit=True,
        ):

            first_name = st.text_input(
                "First Name *",
                max_chars=100,
            )

            last_name = st.text_input(
                "Last Name *",
                max_chars=100,
            )

            email = st.text_input(
                "Work Email *",
                max_chars=255,
            )

            employee_id = st.text_input(
                "Employee ID *",
                max_chars=30,
                placeholder="BM-EMP-1002",
            )

            new_role = st.selectbox(
                "Initial Administrator Role *",
                role_options,
                index=role_default,
                format_func=lambda value: ROLE_LABELS[value],
            )

            if new_role == "super_admin":
                st.warning(
                    "Super Admin receives full access. "
                    "Grant this role only to trusted employees."
                )

            password = st.text_input(
                "Initial Password *",
                type="password",
                help=(
                    "12–72 UTF-8 bytes. Share securely; "
                    "do not send passwords in ordinary email."
                ),
            )

            password_confirm = st.text_input(
                "Confirm Password *",
                type="password",
            )

            reason = st.text_area(
                "Reason for Creating Administrator *",
                max_chars=500,
                placeholder=(
                    "Explain the employee's "
                    "administrative responsibilities."
                ),
            )

            confirmed = st.checkbox(
                "I confirm this employee is authorized "
                "to receive administrator access."
            )

            create_submitted = st.form_submit_button(
                "Create Administrator",
                type="primary",
            )

        # ------------------------------------------
        # SAVE NEW ADMINISTRATOR
        # ------------------------------------------

        if create_submitted:

            if not confirmed:
                st.error(
                    "Confirm that this employee is authorized."
                )

            elif password != password_confirm:
                st.error(
                    "Passwords do not match."
                )

            else:

                try:
                    create_admin_employee(
                        actor_id=admin_id,
                        first_name=first_name,
                        last_name=last_name,
                        email=email,
                        employee_id=employee_id,
                        password=password,
                        role=new_role,
                        reason=reason,
                    )

                except (PermissionError, ValueError) as exc:
                    st.error(str(exc))

                else:
                    st.session_state[
                        "bm_admin_users_flash"
                    ] = (
                        "Administrator account created "
                        "and audited successfully."
                    )

                    st.rerun()

    # ==================================================
    # TAB 3 — ASSIGN OR CHANGE ROLE
    # ==================================================

    with assign_tab:

        st.subheader(
            "Assign / Change Administrator Role"
        )

        st.info(
            "Super Admin grants full system access. "
            "Assign it only to trusted employees."
        )

        candidates = [
            item
            for item in administrators
            if item["active"]
            and item["user_id"] != admin_id
        ]

        if not candidates:

            st.warning(
                "No other active administrator accounts "
                "are eligible for role changes."
            )

        else:

            by_id = {
                item["user_id"]: item
                for item in candidates
            }

            with st.form(
                "bm_admin_role_assignment_form"
            ):

                target_id = st.selectbox(
                    "Select Administrator",
                    options=list(by_id),
                    format_func=lambda value: (
                        f"{by_id[value]['name']} "
                        f"({by_id[value]['email']})"
                    ),
                )

                current_role = by_id[target_id]["role"]

                st.caption(
                    "Current role: "
                    + ROLE_LABELS.get(
                        current_role,
                        "Unassigned",
                    )
                )

                default_index = (
                    ROLES.index(current_role)
                    if current_role in ROLES
                    else 0
                )

                selected_role = st.selectbox(
                    "New Administrator Role",
                    options=list(ROLES),
                    index=default_index,
                    format_func=lambda role: ROLE_LABELS[role],
                )

                reason = st.text_area(
                    "Reason for Role Assignment",
                    max_chars=500,
                    placeholder=(
                        "Explain why this role change "
                        "is authorized."
                    ),
                )

                confirmed = st.checkbox(
                    "I have verified that this administrator "
                    "requires the selected permissions."
                )

                submitted = st.form_submit_button(
                    "Save Role Assignment",
                    type="primary",
                )

            # --------------------------------------
            # PROCESS ROLE CHANGE
            # --------------------------------------

            if submitted and not confirmed:

                st.error(
                    "Please confirm the administrator's "
                    "permission requirements."
                )

            elif submitted:

                try:
                    assign_admin_role(
                        actor_id=admin_id,
                        target_admin_id=int(target_id),
                        new_role=selected_role,
                        reason=reason,
                    )

                except (ValueError, PermissionError) as exc:
                    st.error(str(exc))

                else:

                    st.session_state[
                        "bm_admin_users_flash"
                    ] = (
                        "Administrator role updated "
                        "and recorded in audit history."
                    )

                    st.rerun()

    # ==================================================
    # TAB 5 — ACTIVATE / DEACTIVATE ADMINISTRATOR
    # ==================================================

    with status_tab:

        st.subheader(
            "Administrator Account Status"
        )

        st.caption(
            "Activate or deactivate administrator "
            "employees without deleting accounts, "
            "changing roles, or removing audit history."
        )

        st.warning(
            "Deactivation immediately removes "
            "administrator permissions on the next "
            "server-side access check. "
            "The employee's existing role is retained."
        )

        # Cannot change own account status.

        candidates = [
            item
            for item in administrators
            if item["user_id"] != admin_id
        ]

        if not candidates:

            st.info(
                "Create another administrator before "
                "managing employee account statuses."
            )

        else:

            by_id = {
                item["user_id"]: item
                for item in candidates
            }

            with st.form(
                "bm_admin_employee_status_form"
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

                currently_active = bool(
                    selected["active"]
                )

                desired_active = not currently_active

                st.write(
                    "**Employee ID:** "
                    f"{selected['employee_id']}"
                )

                st.write(
                    "**Assigned Role:** "
                    f"{selected['role_label']}"
                )

                st.write(
                    "**Current Status:** "
                    + (
                        "Active"
                        if currently_active
                        else "Inactive"
                    )
                )

                action_label = (
                    "Deactivate Administrator"
                    if currently_active
                    else "Reactivate Administrator"
                )

                if (
                    selected["role"] == "super_admin"
                    and currently_active
                ):
                    st.warning(
                        "Super Admin accounts are protected. "
                        "The last active Super Admin "
                        "cannot be deactivated."
                    )

                reason = st.text_area(
                    "Reason for Account Status Change *",
                    max_chars=500,
                    placeholder=(
                        "Explain why this administrator "
                        "must be activated or deactivated."
                    ),
                )

                confirmed = st.checkbox(
                    "I confirm this administrator account "
                    "status change is authorized."
                )

                submitted = st.form_submit_button(
                    action_label,
                    type="primary",
                )

            if submitted and not confirmed:

                st.error(
                    "Please confirm that this account "
                    "status change is authorized."
                )

            elif submitted:

                try:
                    set_admin_employee_active(
                        actor_id=admin_id,
                        target_admin_id=int(target_id),
                        active=desired_active,
                        reason=reason,
                    )

                except (
                    PermissionError,
                    ValueError,
                ) as exc:

                    st.error(str(exc))

                else:

                    st.session_state[
                        "bm_admin_users_flash"
                    ] = (
                        "Administrator account "
                        + (
                            "reactivated"
                            if desired_active
                            else "deactivated"
                        )
                        + " successfully. "
                        "The action was recorded "
                        "in audit history."
                    )

                    st.rerun()

    # ==================================================
    # TAB 6 — PASSWORD RESET
    # ==================================================

    with reset_tab:

        render_super_admin_password_reset(
            admin_id=admin_id,
            administrators=administrators,
        )

    # ==================================================
    # TAB 7 — ACCOUNT RECOVERY
    # ==================================================

    with recovery_tab:

        render_admin_lockout_recovery(
            admin_id=admin_id,
            administrators=administrators,
        )
    # ==================================================
    # TAB 8 — SECURITY MONITORING
    # ==================================================

    with security_tab:

        render_admin_security_monitoring(
            admin_id=admin_id,
        )
    # ==================================================
    # TAB 4 — AUDIT HISTORY
    # ==================================================

    with audit_tab:

        st.subheader(
            "Administrator Role and Creation History"
        )

        rows = [
            {
                "Timestamp (UTC)": _timestamp(
                    item["timestamp"]
                ),
                "Changed By (User ID)": item[
                    "actor_user_id"
                ],
                "Administrator (User ID)": item[
                    "target_user_id"
                ],
                "Previous Role": ROLE_LABELS.get(
                    item["previous_role"],
                    "Unassigned",
                ),
                "New Role": ROLE_LABELS.get(
                    item["new_role"],
                    item["new_role"],
                ),
                "Action": item["action"],
                "Reason": item["reason"],
            }
            for item in audit_events
        ]

        if rows:

            st.dataframe(
                rows,
                hide_index=True,
                use_container_width=True,
            )

        else:

            st.info(
                "No administrator account or "
                "role changes recorded."
            )

        st.caption(
            "Showing up to 100 recent events. "
            "Timestamps are in UTC."
        )
