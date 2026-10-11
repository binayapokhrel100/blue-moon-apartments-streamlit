
"""Maintenance requests page for the Blue Moon Apartments resident portal.

Uses Streamlit's HTML renderer for decorative card/timeline markup so the
markup does not get interpreted as Markdown code blocks.
"""

import html
import re
from textwrap import dedent

import streamlit as st

from components.cards import metric_card
from components.header import render_header
from core.session import get_current_user
from services.maintenance_service import (
    create_maintenance_request,
    get_maintenance_request_detail,
    get_maintenance_requests_for_user,
)


CATEGORY_OPTIONS = [
    "Plumbing",
    "Electrical",
    "HVAC",
    "Appliance",
    "Pest Control",
    "Door / Lock",
    "General Repair",
    "Other",
]

URGENCY_OPTIONS = [
    "Low",
    "Medium",
    "High",
    "Emergency",
]


def _safe_text(value) -> str:
    """Escape database/user-supplied text before inserting into HTML."""
    return html.escape(
        str(value if value is not None else ""),
        quote=True,
    )


def _css_suffix(value: str) -> str:
    """Only allow safe characters in a CSS class suffix."""
    return re.sub(
        r"[^a-z0-9-]+",
        "-",
        value.lower().strip(),
    ).strip("-")


def _format_datetime(value) -> str:
    if value is None:
        return "Not available"

    return value.strftime(
        "%b %d, %Y %I:%M %p"
    ).replace(" 0", " ")


def _schedule_text(start, end) -> str:
    if start is None:
        return "Not scheduled"

    if end is None:
        return _format_datetime(start)

    if start.date() == end.date():
        date_text = start.strftime(
            "%b %d, %Y"
        ).replace(" 0", " ")

        start_time = start.strftime(
            "%I:%M %p"
        ).lstrip("0")

        end_time = end.strftime(
            "%I:%M %p"
        ).lstrip("0")

        return (
            f"{date_text} · "
            f"{start_time} – {end_time}"
        )

    return (
        f"{_format_datetime(start)} – "
        f"{_format_datetime(end)}"
    )


def _render_request_card(request: dict) -> None:
    """Render a resident maintenance request using existing project CSS."""

    request_number = _safe_text(
        request["request_number"]
    )

    category = _safe_text(
        request["category"]
    )

    description = _safe_text(
        request["description"]
    )

    urgency = _safe_text(
        request["urgency"]
    )

    status = _safe_text(
        request["status"]
    )

    location = _safe_text(
        request.get("location_detail")
        or "Not specified"
    )

    technician = _safe_text(
        request.get("technician_name")
        or "Not assigned"
    )

    status_class = _css_suffix(
        str(request["status"])
    )

    urgency_class = _css_suffix(
        str(request["urgency"])
    )

    schedule = _safe_text(
        _schedule_text(
            request.get("scheduled_start"),
            request.get("scheduled_end"),
        )
    )

    submitted_date = _safe_text(
        _format_datetime(
            request.get("created_at")
        )
    )

    # st.html renders HTML without interpreting it
    # as an indented Markdown code block.
    st.html(
        dedent(
            f"""
            <div class="maintenance-card">

                <div class="maintenance-card-top">

                    <div>
                        <div class="maintenance-request-number">
                            {request_number}
                        </div>

                        <div class="maintenance-category">
                            {category}
                        </div>
                    </div>

                    <div class="maintenance-badges">
                        <span class="maintenance-status status-{status_class}">
                            {status}
                        </span>

                        <span class="urgency-badge urgency-{urgency_class}">
                            {urgency}
                        </span>
                    </div>

                </div>

                <div class="maintenance-description">
                    {description}
                </div>

                <div class="maintenance-info-grid">

                    <div>
                        <span>Location</span>
                        <strong>{location}</strong>
                    </div>

                    <div>
                        <span>Technician</span>
                        <strong>{technician}</strong>
                    </div>

                    <div>
                        <span>Schedule</span>
                        <strong>{schedule}</strong>
                    </div>

                    <div>
                        <span>Submitted</span>
                        <strong>{submitted_date}</strong>
                    </div>

                </div>

            </div>
            """
        ).strip()
    )


def _render_activity_timeline(
    updates: list[dict],
) -> None:
    """Render the maintenance request activity history."""

    # Preserve the order provided by the service.
    for update in updates:

        update_status = _safe_text(
            update["status"]
        )

        update_message = _safe_text(
            update["message"]
        )

        update_date = _safe_text(
            _format_datetime(
                update.get("created_at")
            )
        )

        st.html(
            dedent(
                f"""
                <div class="maintenance-timeline-item">

                    <div class="timeline-dot"></div>

                    <div class="timeline-content">

                        <strong>
                            {update_status}
                        </strong>

                        <p>
                            {update_message}
                        </p>

                        <span>
                            {update_date}
                        </span>

                    </div>

                </div>
                """
            ).strip()
        )


def render_maintenance() -> None:
    """Render the complete resident maintenance page."""

    # ==========================================
    # CURRENT USER
    # ==========================================

    user = get_current_user() or {}

    user_id = user.get("id")

    if user_id is None:
        st.error(
            "Unable to identify the current resident."
        )
        return

    # ==========================================
    # SUCCESS MESSAGE
    # ==========================================

    if "maintenance_success" in st.session_state:
        st.success(
            st.session_state.pop(
                "maintenance_success"
            )
        )

    # ==========================================
    # LOAD MAINTENANCE REQUESTS
    # ==========================================

    requests = get_maintenance_requests_for_user(
        user_id
    )

    active_requests = [
        item
        for item in requests
        if item["status"] not in {
            "Completed",
            "Cancelled",
        }
    ]

    completed_requests = [
        item
        for item in requests
        if item["status"] == "Completed"
    ]

    emergency_requests = [
        item
        for item in active_requests
        if item["urgency"] == "Emergency"
    ]

    # ==========================================
    # PAGE HEADER
    # ==========================================

    render_header("Maintenance")

    st.html(
        dedent(
            """
            <h1 class="page-title">
                Maintenance
            </h1>

            <p class="page-description">
                Submit maintenance requests and track
                repair progress for your apartment.
            </p>
            """
        ).strip()
    )

    # ==========================================
    # SUMMARY METRICS
    # ==========================================

    col1, col2, col3 = st.columns(3)

    with col1:
        metric_card(
            "Active Requests",
            str(len(active_requests)),
            "Currently open",
        )

    with col2:
        metric_card(
            "Completed",
            str(len(completed_requests)),
            "Resolved requests",
        )

    with col3:
        metric_card(
            "Emergency",
            str(len(emergency_requests)),
            "Active emergency requests",
        )

    st.html("<br>")

    # ==========================================
    # MAINTENANCE TABS
    # ==========================================

    requests_tab, submit_tab = st.tabs(
        [
            "My Requests",
            "Submit Request",
        ]
    )

    # ==========================================
    # TAB 1: MY REQUESTS
    # ==========================================

    with requests_tab:

        if not requests:
            st.info(
                "You have not submitted any "
                "maintenance requests."
            )

        for request in requests:

            # Display the maintenance card.
            _render_request_card(request)

            # ==================================
            # REQUEST ACTIVITY
            # ==================================

            with st.expander(
                "View activity — "
                f"{request['request_number']}"
            ):

                detail = (
                    get_maintenance_request_detail(
                        request_id=request["id"],
                        user_id=user_id,
                    )
                )

                if (
                    detail is None
                    or not detail.get("updates")
                ):
                    st.info(
                        "No activity is available yet."
                    )

                else:
                    _render_activity_timeline(
                        detail["updates"]
                    )

    # ==========================================
    # TAB 2: SUBMIT REQUEST
    # ==========================================

    with submit_tab:

        st.html(
            dedent(
                """
                <div class="section-heading">

                    <h3>
                        New Maintenance Request
                    </h3>

                    <p>
                        Tell us what is wrong and our
                        maintenance team will review
                        the request.
                    </p>

                </div>
                """
            ).strip()
        )

        # ======================================
        # REQUEST FORM
        # ======================================

        with st.form(
            "maintenance_request_form",
            clear_on_submit=False,
        ):

            # Issue category
            category = st.selectbox(
                "Issue category",
                CATEGORY_OPTIONS,
            )

            # Location
            location_detail = st.text_input(
                "Location in apartment",
                placeholder=(
                    "Example: Kitchen sink, "
                    "master bathroom, bedroom"
                ),
            )

            # Urgency
            urgency = st.selectbox(
                "Urgency",
                URGENCY_OPTIONS,
                index=1,
            )

            # Issue description
            description = st.text_area(
                "Describe the issue",
                placeholder=(
                    "Describe what is happening, "
                    "when it started, and any "
                    "important details."
                ),
                height=150,
            )

            # Emergency warning
            if urgency == "Emergency":
                st.warning(
                    "For life-threatening emergencies, "
                    "fire, gas leaks, or immediate danger, "
                    "contact emergency services or "
                    "property management directly."
                )

            # Submit button
            submitted = st.form_submit_button(
                "Submit Maintenance Request",
                use_container_width=True,
            )

        # ======================================
        # PROCESS SUBMISSION
        # ======================================

        if submitted:

            try:
                new_request = (
                    create_maintenance_request(
                        user_id=user_id,
                        category=category,
                        description=description,
                        urgency=urgency,
                        location_detail=location_detail,
                    )
                )

                st.session_state[
                    "maintenance_success"
                ] = (
                    "Maintenance request "
                    f"{new_request['request_number']} "
                    "was submitted successfully."
                )

                st.rerun()

            except ValueError as error:
                st.error(str(error))
