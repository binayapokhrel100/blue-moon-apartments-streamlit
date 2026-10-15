
"""Sprint 09 — Administrator tenant and lease management."""

from core.admin_tenant_workflows import get_tenant_workflows
from services.admin_rbac_service import get_my_admin_access
from datetime import date, timedelta
from views.admin_tenant_history import (
    render_admin_tenant_history,
)
from services.admin_moveout_inspection_service import (
    get_blocked_apartment_ids,
)
from views.admin_deposit_settlements import (
    render_admin_deposit_settlements,
)

from views.admin_moveout_inspections import (
    render_admin_moveout_inspections,
)

import streamlit as st
from sqlalchemy.exc import IntegrityError

from core.session import get_current_user
from services.admin_directory_service import get_admin_directory
from services.admin_management_service import (
    create_resident,
    update_resident,
)
from views.admin_apartment_transfer import (
    render_admin_apartment_transfer,
)
from views.admin_lease_renewal import render_admin_lease_renewal
from views.admin_tenancy_actions import (
    render_archive_tenant,
    render_lease_moveout,
)


# ==========================================================
# SAVE HANDLER
# ==========================================================

def _save_result(
    action,
    message: str,
    revision_key: str,
) -> None:

    try:
        action()

    except (ValueError, PermissionError) as exc:
        st.error(str(exc))

    except IntegrityError:
        st.error(
            "A database constraint was triggered. "
            "Please refresh and try again."
        )

    else:
        st.session_state[revision_key] = (
            st.session_state.get(revision_key, 0) + 1
        )

        st.session_state["admin_tenant_flash"] = message
        st.rerun()


# ==========================================================
# AVAILABLE APARTMENTS
# ==========================================================

def _get_available_apartments(
    apartments: list[dict],
    residents: list[dict],
    exclude_resident_id: int | None = None,
    blocked_apartment_ids: set[int] | None = None,
) -> list[dict]:
    """
    Find currently available units.

    An apartment must:
    - Not be marked occupied.
    - Not be assigned to another resident.

    This is for the interface only.
    The database service validates availability again.
    """

    assigned_ids = {
        resident["apartment_id"]
        for resident in residents
        if resident["apartment_id"] is not None
        and resident["id"] != exclude_resident_id
    }
    blocked = blocked_apartment_ids or set()

    return [
        apartment
        for apartment in apartments
        if (
            not apartment["is_occupied"]
            and apartment["id"] not in assigned_ids
            and apartment["id"] not in blocked
        )
    ]


# ==========================================================
# MAIN TENANT PAGE
# ==========================================================

def render_admin_tenants() -> None:

    user = get_current_user() or {}

    if str(user.get("role", "")).strip().lower() != "admin":
        st.error("Administrator access required.")
        st.stop()

    admin_id = int(user["id"])
    # ==================================================
    # VERIFY ADMINISTRATOR ROLE AND PERMISSIONS
    # ==================================================

    try:
        access = get_my_admin_access(admin_id)

    except (PermissionError, ValueError) as exc:
        st.error(str(exc))
        st.stop()

    permissions = set(
        access["permissions"]
    )

    workflows = get_tenant_workflows(
        permissions
    )

    if not workflows:
        st.error(
            "You do not have permission to access "
            "Tenant Management."
        )
        st.stop()

    workflow_labels = dict(
        workflows
    )

    # Remove a previously selected workflow if the
    # administrator's permissions have changed.

    if (
        st.session_state.get("bm_tenant_workflow")
        not in workflow_labels
    ):
        st.session_state.pop(
            "bm_tenant_workflow",
            None,
        )

    selected_workflow = st.selectbox(
        "Select Tenant Workflow",
        options=list(workflow_labels),
        format_func=lambda value: workflow_labels[value],
        key="bm_tenant_workflow",
    )


    st.title("Tenant Management")

    st.caption(
        "Manage resident information, lease onboarding, "
        "and apartment assignments."
    )

    flash = st.session_state.pop(
        "admin_tenant_flash",
        None,
    )

    if flash:
        st.success(flash)


    # ==================================================
    # LOAD DIRECTORY DATA ONLY WHEN REQUIRED
    # ==================================================

    needs_directory = selected_workflow in {
        "directory",
        "create",
        "edit",
    }

    if needs_directory:

        try:
            data = get_admin_directory(
                admin_id
            )

            blocked_apartment_ids = (
                get_blocked_apartment_ids(
                    admin_id
                )
            )

        except (PermissionError, ValueError) as exc:
            st.error(str(exc))
            return

        residents = data["residents"]
        apartments = data["apartments"]

    else:
        # Inspection, finance, lease, and reporting
        # workflows use their own authorized services.
        residents = []
        apartments = []
        blocked_apartment_ids = set()

    apartment_by_id = {
        unit["id"]: unit
        for unit in apartments
    }

    # ==================================================
    # RESIDENT DIRECTORY SUMMARY
    # ==================================================

    if needs_directory:

        c1, c2, c3 = st.columns(3)

        c1.metric(
            "Resident Accounts",
            len(residents),
        )

        c2.metric(
            "Active Residents",
            sum(
                r["is_active"]
                for r in residents
            ),
        )

        c3.metric(
            "Residents with Active Lease",
            sum(
                r["has_active_lease"]
                for r in residents
            ),
        )


    # ------------------------------------------
    # SUMMARY METRICS
    # ------------------------------------------

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "Resident Accounts",
        len(residents),
    )

    c2.metric(
        "Active Residents",
        sum(r["is_active"] for r in residents),
    )

    c3.metric(
        "Residents with Active Lease",
        sum(r["has_active_lease"] for r in residents),
    )

    # ==================================================
    # TAB 1 — RESIDENT DIRECTORY
    # ==================================================

    if selected_workflow == "directory":

        search_col, status_col, unit_col = st.columns(
            [2, 1, 1]
        )

        with search_col:
            search = st.text_input(
                "Search residents",
                placeholder="Name, email, phone, or unit",
                key="admin_tenant_search",
            ).strip().casefold()

        with status_col:
            status = st.selectbox(
                "Account status",
                ["All", "Active", "Inactive"],
                key="admin_tenant_filter_status",
            )

        with unit_col:
            units = (
                ["All apartments", "Unassigned"]
                + [unit["unit"] for unit in apartments]
            )

            unit_filter = st.selectbox(
                "Apartment",
                list(dict.fromkeys(units)),
                key="admin_tenant_filter_unit",
            )

        matching = []

        for resident in residents:

            searchable = " ".join(
                str(resident[key])
                for key in (
                    "name",
                    "email",
                    "phone",
                    "unit",
                )
            ).casefold()

            if search and search not in searchable:
                continue

            if status == "Active" and not resident["is_active"]:
                continue

            if status == "Inactive" and resident["is_active"]:
                continue

            if (
                unit_filter != "All apartments"
                and resident["unit"] != unit_filter
            ):
                continue

            matching.append(resident)

        st.caption(
            f"Showing {len(matching)} of "
            f"{len(residents)} resident accounts"
        )

        st.dataframe(
            [
                {
                    "Resident": r["name"],
                    "Email": r["email"],
                    "Phone": r["phone"] or "—",
                    "Apartment": r["unit"],
                    "Status": (
                        "Active" if r["is_active"] else "Inactive"
                    ),
                    "Active Lease": (
                        "Yes" if r["has_active_lease"] else "No"
                    ),
                    "Joined": r["joined"],
                }
                for r in matching
            ],
            hide_index=True,
            use_container_width=True,
        )

    # ==================================================
    # TAB 2 — ADD RESIDENT
    # ==================================================

    if selected_workflow == "create":

        st.subheader("Add a New Resident")

        st.caption(
            "A new resident must receive an available "
            "apartment and an active lease."
        )

        vacant_apartments = _get_available_apartments(
            apartments,
            residents,
            blocked_apartment_ids=blocked_apartment_ids,
        )

        vacant_by_id = {
            unit["id"]: unit
            for unit in vacant_apartments
        }

        if not vacant_by_id:

            st.warning(
                "No available apartments. Create a new "
                "vacant apartment or resolve an existing "
                "assignment before adding a resident."
            )

        else:

            revision = st.session_state.get(
                "admin_tenant_create_revision",
                0,
            )

            prefix = f"admin_add_{revision}"

            with st.form(
                f"admin_add_resident_form_{revision}"
            ):

                a, b = st.columns(2)

                with a:
                    first = st.text_input(
                        "First name *",
                        key=f"{prefix}_first",
                    )

                with b:
                    last = st.text_input(
                        "Last name *",
                        key=f"{prefix}_last",
                    )

                mail = st.text_input(
                    "Email address *",
                    key=f"{prefix}_email",
                )

                phone = st.text_input(
                    "Phone (optional)",
                    key=f"{prefix}_phone",
                )

                password = st.text_input(
                    "Temporary password *",
                    type="password",
                    help="12–72 UTF-8 bytes.",
                    key=f"{prefix}_password",
                )

                # ----------------------------------
                # REQUIRED VACANT APARTMENT
                # ----------------------------------

                apartment_id = st.selectbox(
                    "Assign apartment *",
                    list(vacant_by_id),
                    format_func=lambda unit_id: (
                        f"Unit {vacant_by_id[unit_id]['unit']} "
                        f"· {vacant_by_id[unit_id]['monthly_rent']}"
                        "/month"
                    ),
                    key=f"{prefix}_apartment",
                )

                st.markdown("#### Active Lease Details")

                st.caption(
                    "The active lease must include today's date."
                )

                start_col, end_col = st.columns(2)

                with start_col:
                    lease_start = st.date_input(
                        "Lease start date *",
                        value=date.today(),
                        key=f"{prefix}_lease_start",
                    )

                with end_col:
                    lease_end = st.date_input(
                        "Lease end date *",
                        value=date.today() + timedelta(days=365),
                        key=f"{prefix}_lease_end",
                    )

                deposit = st.number_input(
                    "Security deposit ($)",
                    min_value=0.0,
                    max_value=99999999.99,
                    value=0.0,
                    step=50.0,
                    format="%.2f",
                    key=f"{prefix}_deposit",
                )

                st.info(
                    "Monthly rent is copied from the apartment. "
                    "Creating a lease does not collect a payment."
                )

                submitted = st.form_submit_button(
                    "Create Resident & Active Lease",
                    type="primary",
                )

            if submitted:

                _save_result(
                    lambda: create_resident(
                        admin_id,
                        first_name=first,
                        last_name=last,
                        email=mail,
                        password=password,
                        phone=phone,
                        apartment_id=apartment_id,
                        lease_start=lease_start,
                        lease_end=lease_end,
                        security_deposit=deposit,
                    ),
                    "Resident and active lease created successfully.",
                    "admin_tenant_create_revision",
                )

    # ==================================================
    # TAB 3 — EDIT RESIDENT
    # ==================================================

    if selected_workflow == "edit":

        st.subheader("Edit Resident")

        if not residents:

            st.info("Create a resident first.")

        else:

            by_id = {
                resident["id"]: resident
                for resident in residents
            }

            resident_id = st.selectbox(
                "Select a resident",
                list(by_id),
                format_func=lambda value: (
                    f"{by_id[value]['name']} "
                    f"· {by_id[value]['email']}"
                ),
                key="admin_edit_resident_select",
            )

            resident = by_id[resident_id]

            current_apartment = resident["apartment_id"]
            has_active_lease = resident["has_active_lease"]


            # ----------------------------------
            # AVAILABLE UNITS FOR THIS RESIDENT
            # ----------------------------------

            available = _get_available_apartments(
                apartments,
                residents,
                exclude_resident_id=resident_id,
                blocked_apartment_ids=blocked_apartment_ids,
            )

            available_ids = [
                unit["id"]
                for unit in available
            ]

            # Keep the resident's own apartment
            # available, even though it is occupied.
            # This allows contact-detail edits.

            if (
                current_apartment is not None
                and current_apartment in apartment_by_id
                and current_apartment not in available_ids
            ):
                available_ids.insert(
                    0,
                    current_apartment,
                )

            if has_active_lease:

                st.warning(
                    "This resident has an active lease. "
                    "Apartment changes and account deactivation "
                    "are locked until the lease is handled."
                )

                # Keep the current apartment fixed.
                assignment_options = [
                    current_apartment
                ]

            else:

                assignment_options = list(
                    dict.fromkeys(
                        [
                            None,
                            *available_ids,
                        ]
                    )
                )

                st.info(
                    "Only available apartments are listed. "
                    "Apartments occupied or assigned to "
                    "other residents cannot be selected."
                )

            # ----------------------------------
            # LABEL AVAILABLE APARTMENTS
            # ----------------------------------

            def apartment_label(value):

                if value is None:
                    return "Unassigned"

                unit = apartment_by_id.get(value)

                if unit is None:
                    return "Unit unavailable"

                if value == current_apartment:
                    return f"Unit {unit['unit']} (Current)"

                return f"Unit {unit['unit']} (Vacant)"

            # ----------------------------------
            # RESET EDIT FORM AFTER SAVING
            # ----------------------------------

            revision = st.session_state.get(
                "admin_tenant_edit_revision",
                0,
            )

            prefix = (
                f"admin_edit_{resident_id}_{revision}"
            )

            with st.form(
                f"admin_edit_resident_form_"
                f"{resident_id}_{revision}"
            ):

                a, b = st.columns(2)

                with a:
                    first = st.text_input(
                        "First name *",
                        value=resident["first_name"],
                        key=f"{prefix}_first",
                    )

                with b:
                    last = st.text_input(
                        "Last name *",
                        value=resident["last_name"],
                        key=f"{prefix}_last",
                    )

                mail = st.text_input(
                    "Email address *",
                    value=resident["email"],
                    key=f"{prefix}_email",
                )

                phone = st.text_input(
                    "Phone",
                    value=resident["phone"],
                    key=f"{prefix}_phone",
                )

                # ----------------------------------
                # RESTRICTED APARTMENT DROPDOWN
                # ----------------------------------

                if current_apartment in assignment_options:
                    selected_index = assignment_options.index(
                        current_apartment
                    )
                else:
                    selected_index = 0

                apartment_id = st.selectbox(
                    "Apartment assignment",
                    assignment_options,
                    index=selected_index,
                    format_func=apartment_label,
                    disabled=has_active_lease,
                    key=f"{prefix}_apartment",
                )

                active = st.checkbox(
                    "Active resident account",
                    value=resident["is_active"],
                    disabled=has_active_lease,
                    key=f"{prefix}_active",
                )

                submitted = st.form_submit_button(
                    "Save Resident Changes",
                    type="primary",
                )

            if submitted:

                _save_result(
                    lambda: update_resident(
                        admin_id,
                        resident_id,
                        first_name=first,
                        last_name=last,
                        email=mail,
                        phone=phone,
                        apartment_id=apartment_id,
                        is_active=active,
                    ),
                    "Resident information updated successfully.",
                    "admin_tenant_edit_revision",
                )

            st.caption(
                "Changing the assignment of a legacy account "
                "without an active lease does not create a new "
                "lease automatically. Lease creation or transfer "
                "requires a separate management workflow."
            )

    # ==================================================
    # TAB 4 — LEASE TERMINATION / MOVE-OUT
    # ==================================================

    if selected_workflow == "lease":
        render_lease_moveout(admin_id)

    # ==================================================
    # TAB 5 — REMOVE / ARCHIVE TENANT
    # ==================================================

    if selected_workflow == "archive":
        render_archive_tenant(admin_id)

    # ==================================================
    # TAB 6 — LEASE RENEWAL
    # ==================================================
    if selected_workflow == "renewal":
        render_admin_lease_renewal(admin_id)
    # ==================================================
    # TAB 7 — APARTMENT TRANSFER
    # ==================================================

    if selected_workflow == "transfer":
        render_admin_apartment_transfer(admin_id)

    # ==================================================
    # TAB 8 — MOVE-OUT INSPECTION
    # ==================================================

    if selected_workflow == "inspection":
        render_admin_moveout_inspections(admin_id)

    # ==================================================
    # TAB 9 — SECURITY DEPOSIT SETTLEMENT
    # ==================================================

    if selected_workflow == "deposit":
        render_admin_deposit_settlements(admin_id)

    # ==================================================
    # TAB 10 — UNIFIED TENANT HISTORY
    # ==================================================

    if selected_workflow == "history":
        render_admin_tenant_history(admin_id)