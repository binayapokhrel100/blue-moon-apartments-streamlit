
"""
Blue Moon Apartments
Admin Apartment Availability Dashboard

Read-only Streamlit dashboard showing:
- Occupied apartments
- Vacant and available apartments
- Inspection holds
- Required repairs
- Awaiting approval
- Lease reservations
- Records needing review
"""

import logging
from collections import Counter

import streamlit as st

from services.admin_apartment_availability_service import (
    AVAILABLE,
    AWAITING_APPROVAL,
    INSPECTION_PENDING,
    NEEDS_REVIEW,
    OCCUPIED,
    REPAIRS_REQUIRED,
    RESERVED,
    STATUS_ORDER,
    get_apartment_availability,
)


logger = logging.getLogger(__name__)


# ==========================================================
# CURRENCY FORMAT
# ==========================================================

def _currency(value) -> str:
    return f"${value:,.2f}"


# ==========================================================
# MAIN AVAILABILITY DASHBOARD
# ==========================================================

def render_admin_apartment_availability(
    admin_id: int,
) -> None:

    st.subheader(
        "Apartment Availability Dashboard"
    )

    st.caption(
        "Live availability based on resident assignments, "
        "lease reservations and inspection holds. "
        "This dashboard does not release apartments."
    )

    # ==================================================
    # LOAD DASHBOARD DATA
    # ==================================================

    try:

        rows = get_apartment_availability(
            admin_id
        )

    except PermissionError as exc:

        st.error(str(exc))
        return

    except Exception:

        logger.exception(
            "Could not load apartment availability dashboard"
        )

        st.error(
            "Unable to load apartment availability records."
        )
        return

    # ==================================================
    # STATUS COUNTS
    # ==================================================

    counts = Counter(
        row["status"]
        for row in rows
    )

    on_hold = sum(
        counts[name]
        for name in (
            INSPECTION_PENDING,
            REPAIRS_REQUIRED,
            AWAITING_APPROVAL,
        )
    )

    # ==================================================
    # MAIN METRICS
    # ==================================================

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "Total Apartments",
        len(rows),
    )

    c2.metric(
        "Occupied",
        counts[OCCUPIED],
    )

    c3.metric(
        "Vacant — Available",
        counts[AVAILABLE],
    )

    c4.metric(
        "Inspection Holds",
        on_hold,
    )

    # ==================================================
    # ADDITIONAL METRICS
    # ==================================================

    c5, c6, c7 = st.columns(3)

    c5.metric(
        "Reserved",
        counts[RESERVED],
    )

    c6.metric(
        "Needs Review",
        counts[NEEDS_REVIEW],
    )

    c7.metric(
        "Repairs Required",
        counts[REPAIRS_REQUIRED],
    )

    if counts[NEEDS_REVIEW]:

        st.warning(
            f"{counts[NEEDS_REVIEW]} apartment(s) have "
            "records requiring administrator review. "
            "They are not considered available."
        )

    if not rows:

        st.info(
            "No apartments found. "
            "Add an apartment in Apartment Management."
        )

        return

    st.divider()

    # ==================================================
    # SEARCH AND FILTER
    # ==================================================

    st.markdown(
        "#### Find an Apartment"
    )

    left, right = st.columns(
        [2, 1]
    )

    with left:

        search = st.text_input(
            "Search by unit or resident",
            placeholder=(
                "Example: A101 or resident name"
            ),
            key="bm_availability_search",
        ).strip().casefold()

    with right:

        status_filter = st.selectbox(
            "Availability status",
            options=("All",) + STATUS_ORDER,
            key="bm_availability_status_filter",
        )

    # ==================================================
    # FILTER APARTMENT ROWS
    # ==================================================

    filtered = [
        row
        for row in rows
        if (
            status_filter == "All"
            or row["status"] == status_filter
        )
        and (
            not search
            or search in str(row["unit"]).casefold()
            or search in row["assigned_residents"].casefold()
        )
    ]

    st.caption(
        f"Showing {len(filtered)} of "
        f"{len(rows)} apartments"
    )

    if not filtered:

        st.info(
            "No apartments match the selected filters."
        )
        return

    # ==================================================
    # APARTMENT AVAILABILITY TABLE
    # ==================================================

    st.dataframe(
        [
            {
                "Unit": row["unit"],
                "Availability": row["status"],
                "Assigned Resident": (
                    row["assigned_residents"]
                ),
                "Floor": row["floor"],
                "Bedrooms": row["bedrooms"],
                "Bathrooms": row["bathrooms"],
                "Listed Rent": _currency(
                    row["listed_rent"]
                ),
                "Repair Estimate": _currency(
                    row["estimated_repairs"]
                ),
                "Next Step": row["detail"],
            }
            for row in filtered
        ],
        hide_index=True,
        use_container_width=True,
    )

    # ==================================================
    # INDIVIDUAL APARTMENT DETAILS
    # ==================================================

    st.markdown(
        "#### Apartment Details"
    )

    by_id = {
        row["apartment_id"]: row
        for row in filtered
    }

    selected_id = st.selectbox(
        "Select an apartment",
        options=list(by_id),
        format_func=lambda value: (
            f"Unit {by_id[value]['unit']} "
            f"— {by_id[value]['status']}"
        ),
        key="bm_availability_selected_apartment",
    )

    selected = by_id[
        selected_id
    ]

    with st.container(
        border=True
    ):

        st.write(
            f"**Unit:** {selected['unit']}"
        )

        st.write(
            "**Current availability:** "
            f"{selected['status']}"
        )

        st.write(
            "**Assigned resident:** "
            f"{selected['assigned_residents']}"
        )

        st.write(
            "**Listed monthly rent:** "
            f"{_currency(selected['listed_rent'])}"
        )

        st.write(
            "**Next step:** "
            f"{selected['detail']}"
        )

        # --------------------------------------
        # INSPECTION DETAILS
        # --------------------------------------

        if selected["inspection_id"] is not None:

            st.write(
                "**Inspection ID:** "
                f"#{selected['inspection_id']}"
            )

            st.write(
                "**Inspection status:** "
                f"{selected['inspection_status'].title()}"
            )

            st.write(
                "**Estimated repair cost "
                "(not a deposit deduction):** "
                f"{_currency(selected['estimated_repairs'])}"
            )

        # --------------------------------------
        # LEASE RESERVATIONS
        # --------------------------------------

        if selected["lease_reservations"]:

            st.write(
                "**Active/future lease reservations:** "
                f"{selected['lease_reservations']}"
            )

        # --------------------------------------
        # ASSIGNMENT ELIGIBILITY
        # --------------------------------------

        if selected["ready_for_assignment"]:

            st.success(
                "This unit is eligible for "
                "a new resident assignment."
            )

        else:

            st.warning(
                "This unit is NOT eligible for "
                "a new resident assignment. "
                "Resolve its existing restrictions first."
            )

    # ==================================================
    # ADMIN GUIDANCE
    # ==================================================

    st.caption(
        "Complete inspection reports and approve release "
        "in Tenant Management → Move-Out Inspection. "
        "For active/future lease conflicts or inconsistent "
        "assignments, review the resident and apartment "
        "records before editing."
    )
