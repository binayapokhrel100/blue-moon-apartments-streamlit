
"""Administrator apartment directory, unit management, and availability."""

import logging

import streamlit as st
from services.admin_rbac_service import get_my_admin_access
from sqlalchemy.exc import IntegrityError

from core.session import get_current_user
from services.admin_directory_service import get_admin_directory
from services.admin_management_service import (
    create_apartment,
    update_apartment,
)
from views.admin_apartment_availability import (
    render_admin_apartment_availability,
)


logger = logging.getLogger(__name__)


# ==========================================================
# ROLE-AWARE APARTMENT WORKFLOWS
# ==========================================================

def get_apartment_workflows(
    permissions: set[str] | frozenset[str],
) -> list[tuple[str, str]]:
    """Return only the workflows allowed for this administrator."""

    workflows = []

    if "admins.manage" in permissions:
        workflows.append(
            ("availability", "Availability Dashboard")
        )

    if "apartments.read" in permissions:
        workflows.append(
            ("directory", "Apartment Directory")
        )

    if "apartments.create" in permissions:
        workflows.append(
            ("create", "Add Apartment")
        )

    if "apartments.update" in permissions:
        workflows.append(
            ("edit", "Edit Apartment")
        )

    return workflows


# ==========================================================
# SAVE RESULT
# ==========================================================

def _save_result(action, message: str) -> None:
    """Save database changes and display feedback."""

    try:
        action()

    except (ValueError, PermissionError) as exc:
        st.error(str(exc))

    except IntegrityError:
        st.error(
            "A database uniqueness constraint was triggered. "
            "Refresh and retry."
        )

    except Exception:
        logger.exception(
            "Apartment management action failed"
        )
        st.error(
            "Unable to save apartment changes. "
            "Check application logs."
        )

    else:
        st.session_state["admin_apartment_flash"] = message
        st.rerun()


# ==========================================================
# APARTMENT FORM FIELDS
# ==========================================================

def _unit_fields(
    prefix: str,
    no_floor: bool,
    apartment: dict | None = None,
) -> dict:
    """
    Shared create/edit form inputs.

    Floor unspecified checkbox is handled outside
    the form for immediate Streamlit reruns.
    """

    current = apartment or {}

    # ------------------------------------------------------
    # UNIT NUMBER
    # ------------------------------------------------------

    unit_number = st.text_input(
        "Unit number *",
        value=current.get("unit", ""),
        key=f"{prefix}_unit",
    )

    c1, c2, c3 = st.columns(3)

    floor_value = current.get("floor")

    # ------------------------------------------------------
    # FLOOR
    # ------------------------------------------------------

    with c1:
        floor = st.number_input(
            "Floor",
            min_value=-5,
            max_value=200,
            value=(
                int(floor_value)
                if floor_value is not None
                else 0
            ),
            step=1,
            disabled=no_floor,
            key=f"{prefix}_floor",
            help=(
                "Uncheck 'Floor unspecified' "
                "to edit this field."
            ),
        )

    # ------------------------------------------------------
    # BEDROOMS
    # ------------------------------------------------------

    with c2:
        bedrooms = st.number_input(
            "Bedrooms",
            min_value=0,
            max_value=20,
            value=int(
                current.get("bedrooms", 1)
            ),
            step=1,
            key=f"{prefix}_beds",
        )

    # ------------------------------------------------------
    # BATHROOMS
    # ------------------------------------------------------

    with c3:
        bathrooms = st.number_input(
            "Bathrooms",
            min_value=0.5,
            max_value=20.0,
            value=float(
                current.get("bathrooms", 1.0)
            ),
            step=0.5,
            key=f"{prefix}_baths",
        )

    # ------------------------------------------------------
    # MONTHLY RENT
    # ------------------------------------------------------

    rent = st.number_input(
        "Monthly rent ($) *",
        min_value=0.01,
        max_value=99999999.99,
        value=float(
            current.get("rent_value", 1200.00)
        ),
        step=25.0,
        format="%.2f",
        key=f"{prefix}_rent",
    )

    return {
        "unit_number": unit_number,
        "floor": (
            None if no_floor else int(floor)
        ),
        "bedrooms": int(bedrooms),
        "bathrooms": bathrooms,
        "monthly_rent": rent,
    }


# ==========================================================
# MAIN APARTMENT MANAGEMENT PAGE
# ==========================================================

def render_admin_apartments() -> None:
    """
    Render apartment management and the
    read-only availability dashboard.
    """

    # ------------------------------------------------------
    # VERIFY ADMIN SESSION
    # ------------------------------------------------------

    session = get_current_user() or {}

    if (
        str(session.get("role", ""))
        .strip()
        .lower()
        != "admin"
    ):
        st.error(
            "Administrator access required."
        )
        st.stop()

    admin_id = int(
        session["id"]
    )
    # ==================================================
    # VERIFY DATABASE-BACKED ADMIN PERMISSIONS
    # ==================================================

    try:
        access = get_my_admin_access(admin_id)

    except (ValueError, PermissionError):
        st.error(
            "Your administrator access could not be verified."
        )
        st.stop()

    permissions = set(
        access["permissions"]
    )

    if "apartments.read" not in permissions:
        st.error(
            "You do not have permission to access "
            "Apartment Management."
        )
        st.stop()



    # ------------------------------------------------------
    # PAGE HEADER
    # ------------------------------------------------------

    st.title(
        "Apartment Management"
    )

    st.caption(
        "Monitor apartment availability, "
        "review unit assignments, "
        "and manage apartment details."
    )

    # ------------------------------------------------------
    # SUCCESS MESSAGES
    # ------------------------------------------------------

    message = st.session_state.pop(
        "admin_apartment_flash",
        None,
    )

    if message:
        st.success(message)

    # ------------------------------------------------------
    # LOAD APARTMENT DIRECTORY
    # ------------------------------------------------------

    try:
        apartments = get_admin_directory(
            admin_id,
            include_residents="tenants.read" in permissions,
            )["apartments"]

    except (ValueError, PermissionError) as exc:
        st.error(str(exc))
        return

    except Exception:
        logger.exception(
            "Unable to load apartment directory"
        )

        st.error(
            "Unable to load apartment records."
        )
        return


    # ==================================================
    # ROLE-AWARE APARTMENT WORKFLOW SELECTOR
    # ==================================================

    workflow_options = get_apartment_workflows(
        permissions
    )

    if not workflow_options:
        st.warning(
            "No apartment workflows are available "
            "for your administrator role."
        )
        return

    workflow_labels = dict(
        workflow_options
    )

    available_workflows = list(
        workflow_labels
    )

    # Reset stale selections if permissions change.

    if (
        st.session_state.get("bm_apartment_workflow")
        not in available_workflows
    ):
        st.session_state.pop(
            "bm_apartment_workflow",
            None,
        )

    selected_workflow = st.selectbox(
        "Select Apartment Workflow",
        options=available_workflows,
        format_func=lambda value: workflow_labels[value],
        key="bm_apartment_workflow",
    )

    # ======================================================
    # TAB 1 — APARTMENT AVAILABILITY DASHBOARD
    # ======================================================

    if selected_workflow == "availability":

        render_admin_apartment_availability(
            admin_id
        )

    # ======================================================
    # TAB 2 — APARTMENT DIRECTORY
    # ======================================================

    if selected_workflow == "directory":

        # --------------------------------------------------
        # OCCUPANCY METRICS
        # --------------------------------------------------

        occupied = sum(
            bool(unit["is_occupied"])
            for unit in apartments
        )

        a, b, c = st.columns(3)

        a.metric(
            "Total Apartments",
            len(apartments),
        )

        b.metric(
            "Marked Occupied",
            occupied,
        )

        c.metric(
            "Marked Vacant",
            len(apartments) - occupied,
        )

        st.caption(
            "These figures reflect stored occupancy "
            "flags only. For actual readiness to "
            "assign, use Availability Dashboard."
        )

        # --------------------------------------------------
        # SEARCH AND FILTERS
        # --------------------------------------------------

        search_col, status_col = st.columns(
            [2, 1]
        )

        with search_col:

            search = st.text_input(
                "Search apartments",
                placeholder=(
                    "Unit number or resident name"
                ),
                key="admin_unit_search",
            ).strip().casefold()

        with status_col:

            status = st.selectbox(
                "Occupancy",
                [
                    "All",
                    "Occupied",
                    "Vacant",
                ],
                key="admin_unit_status",
            )

        # --------------------------------------------------
        # FILTER DIRECTORY
        # --------------------------------------------------

        matching = []

        for unit in apartments:

            haystack = (
                f"{unit['unit']} "
                f"{unit['resident_names']}"
            ).casefold()

            if search and search not in haystack:
                continue

            if (
                status == "Occupied"
                and not unit["is_occupied"]
            ):
                continue

            if (
                status == "Vacant"
                and unit["is_occupied"]
            ):
                continue

            matching.append(unit)

        st.caption(
            f"Showing {len(matching)} of "
            f"{len(apartments)} apartments"
        )

        # --------------------------------------------------
        # DIRECTORY TABLE
        # --------------------------------------------------

        st.dataframe(
            [
                {
                    "Unit": unit["unit"],

                    "Floor": (
                        unit["floor"]
                        if unit["floor"] is not None
                        else "—"
                    ),

                    "Beds": unit["bedrooms"],

                    "Baths": unit["bathrooms"],

                    "Monthly Rent": (
                        unit["monthly_rent"]
                    ),

                    "Occupancy": (
                        "Occupied"
                        if unit["is_occupied"]
                        else "Vacant"
                    ),

                    "Active Residents": (
                        unit["resident_count"]
                    ),

                    "Assigned Residents": (
                        unit["resident_names"]
                    ),
                }
                for unit in matching
            ],
            hide_index=True,
            use_container_width=True,
        )

        # --------------------------------------------------
        # APARTMENT DETAILS
        # --------------------------------------------------

        if matching:

            options = {
                unit["id"]: unit
                for unit in matching
            }

            selected = st.selectbox(
                "Inspect a unit",
                list(options),
                format_func=lambda uid: (
                    f"Unit {options[uid]['unit']}"
                ),
                key="admin_unit_inspect",
            )

            unit = options[selected]

            with st.container(
                border=True
            ):

                st.write(
                    f"**Unit:** {unit['unit']}"
                )

                st.write(
                    "**Monthly rent:** "
                    f"{unit['monthly_rent']}"
                )

                st.write(
                    "**Bedrooms / bathrooms:** "
                    f"{unit['bedrooms']} / "
                    f"{unit['bathrooms']}"
                )

                st.write(
                    "**Assigned active residents:** "
                    f"{unit['resident_names']}"
                )

                # ------------------------------------------
                # OCCUPANCY INCONSISTENCY WARNING
                # ------------------------------------------

                if (
                    unit["is_occupied"]
                    != (
                        unit["resident_count"] > 0
                    )
                ):

                    st.warning(
                        "Recorded occupancy and active "
                        "resident assignments differ. "
                        "There may be an active lease "
                        "or an older occupancy flag."
                    )

    # ======================================================
    # TAB 3 — CREATE APARTMENT
    # ======================================================

    if selected_workflow == "create":

        st.subheader(
            "Create a New Apartment"
        )

        st.caption(
            "New units start vacant. "
            "Add and assign residents from "
            "Tenant Management."
        )

        # --------------------------------------------------
        # FLOOR CHECKBOX OUTSIDE FORM
        # --------------------------------------------------

        no_floor_create = st.checkbox(
            "Floor unspecified",
            value=False,
            key="admin_add_unit_no_floor",
            help=(
                "Check this if the apartment "
                "does not have a specified floor."
            ),
        )

        # --------------------------------------------------
        # CREATE FORM
        # --------------------------------------------------

        with st.form(
            "admin_create_apartment_form"
        ):

            values = _unit_fields(
                prefix="admin_add_unit",
                no_floor=no_floor_create,
            )

            submitted = st.form_submit_button(
                "Create Apartment",
                type="primary",
            )

        if submitted:

            _save_result(
                lambda: create_apartment(
                    admin_id,
                    **values,
                ),
                "Apartment created successfully.",
            )

    # ======================================================
    # TAB 4 — EDIT APARTMENT
    # ======================================================

    if selected_workflow == "edit":

        st.subheader(
            "Update an Existing Apartment"
        )

        if not apartments:

            st.info(
                "Create an apartment first."
            )

        else:

            # ------------------------------------------------
            # SELECT APARTMENT
            # ------------------------------------------------

            options = {
                unit["id"]: unit
                for unit in apartments
            }

            apartment_id = st.selectbox(
                "Select apartment",
                list(options),
                format_func=lambda uid: (
                    f"Unit {options[uid]['unit']}"
                ),
                key="admin_unit_edit_select",
            )

            unit = options[
                apartment_id
            ]

            # ------------------------------------------------
            # FLOOR CHECKBOX OUTSIDE FORM
            # ------------------------------------------------

            no_floor_edit = st.checkbox(
                "Floor unspecified",
                value=unit["floor"] is None,
                key=(
                    f"admin_edit_unit_"
                    f"{apartment_id}_no_floor"
                ),
                help=(
                    "Check to remove the floor value. "
                    "Uncheck to specify a floor."
                ),
            )

            # ------------------------------------------------
            # EDIT FORM
            # ------------------------------------------------

            with st.form(
                f"admin_edit_unit_form_"
                f"{apartment_id}"
            ):

                values = _unit_fields(
                    prefix=(
                        f"admin_edit_unit_"
                        f"{apartment_id}"
                    ),
                    no_floor=no_floor_edit,
                    apartment=unit,
                )

                submitted = st.form_submit_button(
                    "Save Apartment Changes",
                    type="primary",
                )

            if submitted:

                _save_result(
                    lambda: update_apartment(
                        admin_id,
                        apartment_id,
                        **values,
                    ),
                    "Apartment changes saved successfully.",
                )

            st.info(
                "Editing the unit's listed monthly rent "
                "does not change any resident's existing "
                "lease terms or historical payments."
            )
