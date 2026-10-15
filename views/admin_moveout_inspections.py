
"""Blue Moon Apartments — Admin Move-Out Inspection UI."""

import logging
from services.admin_rbac_service import get_my_admin_access
import streamlit as st
from sqlalchemy.exc import IntegrityError

from services.admin_moveout_inspection_service import (
    CONDITION_OPTIONS,
    approve_inspection,
    get_inspection_history,
    get_open_inspections,
    record_inspection,
)


logger = logging.getLogger(__name__)


# ==========================================================
# SAVE RESULT HANDLER
# ==========================================================

def _run_action(action, message: str) -> None:

    try:
        action()

    except (ValueError, PermissionError) as exc:
        st.error(str(exc))

    except IntegrityError:
        st.error(
            "The database rejected this change. "
            "Refresh and try again."
        )

    except Exception:
        logger.exception("Move-out inspection action failed")
        st.error(
            "Unable to complete this inspection action."
        )

    else:
        st.session_state["bm_inspection_flash"] = message
        st.rerun()


# ==========================================================
# CONDITION SELECTOR HELPER
# ==========================================================

def _condition_index(value: str | None) -> int:
    if value in CONDITION_OPTIONS:
        return CONDITION_OPTIONS.index(value)
    return 0


# ==========================================================
# MAIN INSPECTION PAGE
# ==========================================================

def render_admin_moveout_inspections(
    admin_id: int,
) -> None:
    # ==================================================
    # INSPECTION ROLE PERMISSIONS
    # ==================================================

    try:
        access = get_my_admin_access(admin_id)

    except (PermissionError, ValueError) as exc:
        st.error(str(exc))
        return

    permissions = set(
        access["permissions"]
    )

    if "inspections.read" not in permissions:
        st.error(
            "You do not have permission to view inspections."
        )
        return

    can_record = "inspections.record" in permissions
    can_approve = "inspections.approve" in permissions

    if not can_record:
        st.info(
            "Inspection records are read-only for your role."
        )


    st.subheader("Move-Out Inspection")

    st.caption(
        "Inspect apartments after move-out or transfer "
        "and approve them for future occupancy."
    )

    flash = st.session_state.pop(
        "bm_inspection_flash",
        None,
    )

    if flash:
        st.success(flash)

    st.info(
        "Pending and Inspected apartments cannot be "
        "assigned to new residents. Only an approved "
        "inspection releases that restriction."
    )

    # ==================================================
    # LOAD INSPECTION QUEUE
    # ==================================================

    try:
        inspections = get_open_inspections(
            admin_id
        )

    except PermissionError as exc:
        st.error(str(exc))
        return

    except Exception:
        logger.exception("Inspection queue loading failed")
        st.error("Unable to load inspection records.")
        return

    pending_count = sum(
        item["status"] == "pending"
        for item in inspections
    )

    inspected_count = sum(
        item["status"] == "inspected"
        for item in inspections
    )

    c1, c2, c3 = st.columns(3)

    c1.metric("Awaiting Inspection", pending_count)
    c2.metric("Awaiting Approval", inspected_count)
    c3.metric("Total On Hold", len(inspections))

    # ==================================================
    # SELECT AN OPEN INSPECTION
    # ==================================================

    if not inspections:
        st.success(
            "There are no apartments currently "
            "waiting for inspection approval."
        )

    else:

        by_id = {
            item["id"]: item
            for item in inspections
        }

        inspection_id = st.selectbox(
            "Select an apartment inspection",
            list(by_id),
            format_func=lambda value: (
                f"Unit {by_id[value]['unit']} "
                f"· {by_id[value]['resident']} "
                f"· {by_id[value]['status'].title()}"
            ),
            key="bm_inspection_selected",
        )

        selected = by_id[
            inspection_id
        ]

        # --------------------------------------
        # INSPECTION SUMMARY
        # --------------------------------------

        with st.container(border=True):

            st.write(
                f"**Apartment:** Unit {selected['unit']}"
            )

            st.write(
                f"**Previous resident:** "
                f"{selected['resident']}"
            )

            st.write(
                f"**Reason for inspection:** "
                f"{selected['source'].replace('_', ' ').title()}"
            )

            st.write(
                f"**Current status:** "
                f"{selected['status'].title()}"
            )

            st.write(
                "**Apartment availability:** "
                "Not available — Inspection Hold"
            )

        # ==================================================
        # REPORT OR UPDATE INSPECTION
        # ==================================================

        st.markdown("#### Inspection Report")

        revision = st.session_state.get(
            "bm_inspection_revision",
            0,
        )

        key_prefix = (
            f"bm_inspection_{inspection_id}_{revision}"
        )

        with st.form(
            f"{key_prefix}_report"
        ):

            c1, c2, c3 = st.columns(3)

            with c1:
                cleanliness = st.selectbox(
                    "Cleanliness *",
                    CONDITION_OPTIONS,
                    index=_condition_index(
                        selected["cleanliness"]
                    ),
                )

            with c2:
                walls_floors = st.selectbox(
                    "Walls and Floors *",
                    CONDITION_OPTIONS,
                    index=_condition_index(
                        selected["walls_floors"]
                    ),
                )

            with c3:
                appliances = st.selectbox(
                    "Appliances *",
                    CONDITION_OPTIONS,
                    index=_condition_index(
                        selected["appliances"]
                    ),
                )

            keys_returned = st.checkbox(
                "All apartment keys were returned",
                value=bool(selected["keys_returned"]),
            )

            access_secured = st.checkbox(
                "Apartment access is secured "
                "(keys returned or locks rekeyed)",
                value=bool(selected["access_secured"]),
            )

            repairs_completed = st.checkbox(
                "All necessary cleaning and repairs "
                "have been completed",
                value=bool(selected["repairs_completed"]),
            )

            damage_notes = st.text_area(
                "Damage / maintenance findings",
                value=selected["damage_notes"],
                placeholder=(
                    "Document any damage, missing items, "
                    "or repairs needed."
                ),
                height=100,
                max_chars=2000,
            )

            estimated_repair_cost = st.number_input(
                "Estimated repair cost ($)",
                min_value=0.0,
                max_value=99999999.99,
                value=selected["estimated_repair_cost"],
                step=25.0,
                format="%.2f",
            )

            notes = st.text_area(
                "Inspection notes *",
                value=selected["inspection_notes"],
                placeholder=(
                    "Describe the apartment condition "
                    "and any follow-up work."
                ),
                height=120,
                max_chars=2000,
            )

            saved = st.form_submit_button(
                (
                    "Update Inspection Report"
                    if selected["status"] == "inspected"
                    else "Save Inspection Report"
                ),
                type="primary",
                disabled=not can_record,
            )

        if saved:

            def save_report():
                record_inspection(
                    admin_id,
                    inspection_id,
                    cleanliness=cleanliness,
                    walls_floors=walls_floors,
                    appliances=appliances,
                    keys_returned=keys_returned,
                    access_secured=access_secured,
                    repairs_completed=repairs_completed,
                    damage_notes=damage_notes,
                    inspection_notes=notes,
                    estimated_repair_cost=estimated_repair_cost,
                )

            _run_action(
                save_report,
                "Inspection report saved successfully.",
            )

        # ==================================================
        # FINAL APPROVAL
        # ==================================================

        if (
            selected["status"] == "inspected"
            and can_approve
            ):

            st.divider()

            st.markdown(
                "#### Approve Apartment Release"
            )

            st.warning(
                "Approval will remove the inspection "
                "hold and make this apartment eligible "
                "for new tenant assignment."
            )

            if not selected["access_secured"]:
                st.warning(
                    "Apartment access must be secured "
                    "before approval."
                )

            needs_repair = any(
                selected[field] == "Needs Repair"
                for field in (
                    "cleanliness",
                    "walls_floors",
                    "appliances",
                )
            )

            if (
                needs_repair
                and not selected["repairs_completed"]
            ):
                st.warning(
                    "Required repairs must be marked "
                    "completed before approval."
                )

            with st.form(
                f"bm_inspection_approve_{inspection_id}"
            ):

                confirmed = st.checkbox(
                    "I confirm the apartment has been "
                    "inspected, is safe to release, "
                    "and all required work is complete."
                )

                approved = st.form_submit_button(
                    "Approve & Release Apartment",
                    type="primary",
                )

            if approved:

                if not confirmed:
                    st.error(
                        "Please confirm the apartment "
                        "release before continuing."
                    )

                else:
                    _run_action(
                        lambda: approve_inspection(
                            admin_id,
                            inspection_id,
                        ),
                        "Inspection approved. "
                        "Apartment released for assignment.",
                    )

    # ==================================================
    # INSPECTION HISTORY
    # ==================================================

    st.divider()
    st.subheader("Inspection History")

    try:
        history = get_inspection_history(
            admin_id
        )

    except PermissionError as exc:
        st.error(str(exc))
        return

    except Exception:
        logger.exception("Inspection history loading failed")
        st.error("Unable to load inspection history.")
        return

    if not history:
        st.caption(
            "No inspection records have been created yet."
        )
        return

    st.dataframe(
        [
            {
                "Unit": row["unit"],
                "Previous Resident": row["resident"],
                "Source": row["source"],
                "Status": row["status"].title(),
                "Inspection Date": row["inspection_date"],
                "Cleanliness": row["cleanliness"] or "—",
                "Walls / Floors": row["walls_floors"] or "—",
                "Appliances": row["appliances"] or "—",
                "Estimated Repairs ($)": (
                    row["estimated_repair_cost"]
                ),
                "Inspected By": row["inspected_by"] or "—",
                "Approved By": row["approved_by"] or "—",
                "Approved At": row["approved_at"],
            }
            for row in history
        ],
        hide_index=True,
        use_container_width=True,
    )
