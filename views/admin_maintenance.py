
"""Sprint 09 — administrator maintenance requests and status updates."""

import logging
from datetime import date, datetime, time

import streamlit as st
from sqlalchemy.exc import IntegrityError

from core.session import get_current_user
from services.admin_operations_service import (
    MAINTENANCE_TRANSITIONS,
    get_admin_maintenance,
    get_maintenance_history,
    update_maintenance_request,
)


logger = logging.getLogger(__name__)


# ==================================================
# DATE FORMATTING
# ==================================================

def _when(
    value: datetime | None,
) -> str:
    """Format a maintenance timestamp."""

    return (
        value.strftime(
            "%b %d, %Y · %I:%M %p"
        )
        if value
        else "—"
    )


# ==================================================
# ADMIN MAINTENANCE PAGE
# ==================================================

def render_admin_maintenance() -> None:
    """Review and manage resident maintenance requests."""

    session = get_current_user() or {}

    role = str(
        session.get("role", "")
    ).strip().lower()

    if role != "admin":
        st.error(
            "Administrator access required."
        )
        st.stop()

    admin_id = int(
        session["id"]
    )

    st.title(
        "Maintenance Management"
    )

    st.caption(
        "Review resident requests, assign technicians, "
        "schedule work and record status updates."
    )

    # ------------------------------------------
    # SUCCESS MESSAGE
    # ------------------------------------------

    message = st.session_state.pop(
        "admin_maintenance_flash",
        None,
    )

    if message:
        st.success(message)

    # ------------------------------------------
    # LOAD MAINTENANCE DATA
    # ------------------------------------------

    try:

        data = get_admin_maintenance(
            admin_id
        )

    except PermissionError:
        st.error(
            "Your administrator account "
            "is not authorized."
        )
        st.stop()

    except Exception:
        logger.exception(
            "Admin maintenance data could not load"
        )
        st.error(
            "Could not load maintenance requests."
        )
        return

    # ------------------------------------------
    # SUMMARY METRICS
    # ------------------------------------------

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "All Requests",
        data["total"],
    )

    c2.metric(
        "Open Requests",
        data["open"],
    )

    c3.metric(
        "Completed Requests",
        data["completed"],
    )

    requests = data["requests"]

    # ------------------------------------------
    # NAVIGATION TABS
    # ------------------------------------------

    directory_tab, update_tab = st.tabs(
        [
            "Request Directory",
            "Update a Request",
        ]
    )

    # ==================================================
    # REQUEST DIRECTORY
    # ==================================================

    with directory_tab:

        c_search, c_status, c_urgency = st.columns(
            [2, 1, 1]
        )

        # --------------------------------------
        # SEARCH
        # --------------------------------------

        with c_search:

            query = st.text_input(
                "Search maintenance",
                placeholder=(
                    "Request number, resident, "
                    "unit or category"
                ),
                key="admin_maint_search",
            ).strip().casefold()

        # --------------------------------------
        # STATUS FILTER
        # --------------------------------------

        with c_status:

            statuses = [
                "All"
            ] + sorted(
                {
                    str(request["status"])
                    for request in requests
                }
            )

            status_filter = st.selectbox(
                "Status",
                statuses,
                key="admin_maint_status_filter",
            )

        # --------------------------------------
        # URGENCY FILTER
        # --------------------------------------

        with c_urgency:

            urgencies = [
                "All"
            ] + sorted(
                {
                    str(request["urgency"])
                    for request in requests
                }
            )

            urgency_filter = st.selectbox(
                "Urgency",
                urgencies,
                key="admin_maint_urgency_filter",
            )

        # --------------------------------------
        # APPLY FILTERS
        # --------------------------------------

        filtered = []

        for request in requests:

            terms = " ".join(
                str(
                    request[field] or ""
                )
                for field in (
                    "number",
                    "resident",
                    "unit",
                    "category",
                    "description",
                )
            ).casefold()

            if (
                query
                and query not in terms
            ):
                continue

            if (
                status_filter != "All"
                and request["status"]
                != status_filter
            ):
                continue

            if (
                urgency_filter != "All"
                and request["urgency"]
                != urgency_filter
            ):
                continue

            filtered.append(request)

        # --------------------------------------
        # REQUEST TABLE
        # --------------------------------------

        st.caption(
            f"Showing {len(filtered)} of "
            f"{len(requests)} recent requests "
            "(up to 200)"
        )

        st.dataframe(
            [
                {
                    "Request": (
                        request["number"]
                    ),
                    "Resident": (
                        request["resident"]
                    ),
                    "Unit": (
                        request["unit"]
                    ),
                    "Category": (
                        request["category"]
                    ),
                    "Urgency": (
                        request["urgency"]
                    ),
                    "Status": (
                        request["status"]
                    ),
                    "Technician": (
                        request["technician"]
                        or "Unassigned"
                    ),
                    "Created (UTC)": _when(
                        request["created_at"]
                    ),
                }
                for request in filtered
            ],
            hide_index=True,
            use_container_width=True,
        )

    # ==================================================
    # UPDATE MAINTENANCE REQUEST
    # ==================================================

    with update_tab:

        if not requests:

            st.info(
                "No maintenance requests "
                "have been submitted yet."
            )
            return

        # --------------------------------------
        # SELECT REQUEST
        # --------------------------------------

        options = {
            request["id"]: request
            for request in requests
        }

        selected_id = st.selectbox(
            "Select a request",
            list(options),
            format_func=lambda rid: (
                f"{options[rid]['number']} "
                f"· Unit {options[rid]['unit']} "
                f"· {options[rid]['category']}"
            ),
            key="admin_maintenance_selected_request",
        )

        current = options[
            selected_id
        ]

        status = str(
            current["status"] or ""
        ).strip()

        # --------------------------------------
        # REQUEST DETAILS
        # --------------------------------------

        with st.container(
            border=True
        ):

            st.markdown(
                f"**Resident:** {current['resident']} "
                f" | **Unit:** {current['unit']}"
            )

            st.write(
                f"**Request:** "
                f"{current['number']} — "
                f"{current['category']}"
            )

            st.write(
                f"**Location:** "
                f"{current['location']}"
            )

            st.write(
                f"**Description:** "
                f"{current['description']}"
            )

            st.write(
                f"**Urgency:** "
                f"{current['urgency']} "
                f" | **Current status:** "
                f"{status}"
            )

            st.caption(
                f"Created: "
                f"{_when(current['created_at'])} "
                f"UTC"
            )

        # --------------------------------------
        # VALIDATE CURRENT STATUS
        # --------------------------------------

        if status not in MAINTENANCE_TRANSITIONS:

            st.warning(
                "This request has an unsupported "
                "status. Review the record "
                "before editing."
            )

        elif not MAINTENANCE_TRANSITIONS[status]:

            st.info(
                "This request is completed or cancelled. "
                "Its history remains available below."
            )

        else:

            # ----------------------------------
            # AVAILABLE STATUS TRANSITIONS
            # ----------------------------------

            choices = [
                status
            ] + sorted(
                MAINTENANCE_TRANSITIONS[
                    status
                ]
            )

            # Update the form key after each
            # successful save so new defaults load.

            revision = st.session_state.get(
                "admin_maint_form_revision",
                0,
            )

            prefix = (
                f"admin_maint_"
                f"{selected_id}_"
                f"{revision}"
            )

            # ----------------------------------
            # DEFAULT APPOINTMENT TIMES
            # ----------------------------------

            default_start = (
                current["start"]
                or datetime.combine(
                    date.today(),
                    time(9, 0),
                )
            )

            default_end = (
                current["end"]
                or datetime.combine(
                    date.today(),
                    time(11, 0),
                )
            )

            # ----------------------------------
            # MAINTENANCE UPDATE FORM
            # ----------------------------------

            with st.form(
                f"admin_update_request_form_"
                f"{selected_id}_{revision}"
            ):

                new_status = st.selectbox(
                    "Change status",
                    choices,
                    key=f"{prefix}_status",
                )

                technician = st.text_input(
                    "Assigned technician",
                    value=(
                        current["technician"]
                    ),
                    max_chars=150,
                    key=f"{prefix}_technician",
                )

                st.caption(
                    "Appointment fields are used "
                    "only when the selected status "
                    "is Scheduled."
                )

                a, b, c = st.columns(3)

                # Appointment date

                with a:

                    appointment_date = st.date_input(
                        "Appointment date",
                        value=(
                            default_start.date()
                        ),
                        key=f"{prefix}_date",
                    )

                # Start time

                with b:

                    start_time = st.time_input(
                        "Start time",
                        value=(
                            default_start.time()
                        ),
                        key=f"{prefix}_start",
                    )

                # End time

                with c:

                    end_time = st.time_input(
                        "End time",
                        value=(
                            default_end.time()
                        ),
                        key=f"{prefix}_end",
                    )

                # Admin note

                note = st.text_area(
                    "Update note",
                    placeholder=(
                        "Explain the maintenance "
                        "update to the resident"
                    ),
                    max_chars=500,
                    key=f"{prefix}_note",
                )

                submitted = (
                    st.form_submit_button(
                        "Save Maintenance Update",
                        type="primary",
                    )
                )

            # ----------------------------------
            # SAVE SUBMISSION
            # ----------------------------------

            if submitted:

                start = None
                end = None

                if new_status == "Scheduled":

                    start = datetime.combine(
                        appointment_date,
                        start_time,
                    )

                    end = datetime.combine(
                        appointment_date,
                        end_time,
                    )

                try:

                    update_maintenance_request(
                        admin_id,
                        selected_id,
                        expected_status=status,
                        new_status=new_status,
                        technician_name=technician,
                        note=note,
                        scheduled_start=start,
                        scheduled_end=end,
                    )

                except (
                    ValueError,
                    PermissionError,
                ) as exc:

                    st.error(
                        str(exc)
                    )

                except IntegrityError:

                    st.error(
                        "The database could not save "
                        "this update. Please refresh "
                        "and retry."
                    )

                else:

                    st.session_state[
                        "admin_maint_form_revision"
                    ] = revision + 1

                    st.session_state[
                        "admin_maintenance_flash"
                    ] = (
                        f"Request {current['number']} "
                        "updated. The resident "
                        "was notified."
                    )

                    st.rerun()

        # --------------------------------------
        # REQUEST HISTORY
        # --------------------------------------

        st.subheader(
            "Request History"
        )

        try:

            history = get_maintenance_history(
                admin_id,
                selected_id,
            )

        except (
            ValueError,
            PermissionError,
        ) as exc:

            st.error(
                str(exc)
            )
            return

        if not history:

            st.caption(
                "No status updates recorded yet."
            )

        else:

            for entry in history:

                with st.container(
                    border=True
                ):

                    st.write(
                        f"**{entry['status']}** "
                        f"— {entry['message']}"
                    )

                    st.caption(
                        f"{_when(entry['at'])} "
                        f"UTC"
                    )

        st.caption(
            "Appointment times use the property's "
            "local clock. This demo does not yet "
            "provide timezone configuration."
        )
