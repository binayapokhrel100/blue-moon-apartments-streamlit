
"""Blue Moon Apartments — admin-only tenant history and CSV reports."""

import csv
import io
import logging
import zipfile
from datetime import date, datetime
from decimal import Decimal

import streamlit as st

from core.session import get_current_user
from services.admin_tenant_history_service import (
    get_history_residents,
    get_resident_history,
)


logger = logging.getLogger(__name__)


# ==========================================================
# CSV EXPORT HELPERS
# ==========================================================

def _csv_safe(value) -> str:
    """Protect CSV exports from spreadsheet formula injection."""

    if value is None:
        return ""

    if isinstance(value, Decimal):
        result = f"{value:.2f}"

    elif isinstance(value, datetime):
        result = value.isoformat(sep=" ")

    elif isinstance(value, date):
        result = value.isoformat()

    else:
        result = str(value)

    if result.lstrip().startswith(
        ("=", "+", "-", "@")
    ):
        return "'" + result

    return result


def _csv_bytes(
    rows: list[dict],
) -> bytes:

    if not rows:
        return b""

    buffer = io.StringIO()

    headers = list(
        dict.fromkeys(
            key
            for row in rows
            for key in row
        )
    )

    writer = csv.DictWriter(
        buffer,
        fieldnames=headers,
        extrasaction="ignore",
    )

    writer.writeheader()

    for row in rows:
        writer.writerow(
            {
                key: _csv_safe(
                    row.get(key)
                )
                for key in headers
            }
        )

    return buffer.getvalue().encode(
        "utf-8-sig"
    )


# ==========================================================
# FORMAT ACTIVITY TIMELINE
# ==========================================================
def _display_timeline(
    events: list[dict],
) -> list[dict]:
    """
    Format timeline records for Streamlit.

    Convert all dates and datetimes to consistent
    strings to prevent PyArrow conversion errors.
    """

    formatted_events = []

    for item in events:

        event_date = item.get("date")

        # --------------------------------------
        # NORMALIZE DATE VALUES
        # --------------------------------------

        if isinstance(event_date, datetime):

            date_display = event_date.strftime(
                "%Y-%m-%d %H:%M:%S"
            )

        elif isinstance(event_date, date):

            date_display = event_date.strftime(
                "%Y-%m-%d"
            )

        elif event_date is None:

            date_display = ""

        else:

            date_display = str(event_date)

        # --------------------------------------
        # FORMAT OPTIONAL AMOUNT
        # --------------------------------------

        amount = item.get("amount")

        if amount is not None:

            amount_display = (
                f"${Decimal(str(amount)):,.2f}"
            )

        else:

            amount_display = ""

        # --------------------------------------
        # BUILD DISPLAY ROW
        # --------------------------------------

        formatted_events.append(
            {
                "Date": date_display,
                "Category": str(
                    item.get("category", "")
                ),
                "Event": str(
                    item.get("event", "")
                ),
                "Details": str(
                    item.get("details", "")
                ),
                "Amount": amount_display,
            }
        )

    return formatted_events

# ==========================================================
# COMPLETE HISTORY REPORT
# ==========================================================

def _full_report_zip(
    history: dict,
) -> bytes:
    """
    Create a complete resident report in memory.

    No database or project files are changed.
    """

    sections = {
        "leases.csv": history["leases"],
        "lease_renewals.csv": history["renewals"],
        "apartment_transfers.csv": history["transfers"],
        "rent_payments.csv": history["payments"],
        "maintenance_requests.csv": history["maintenance"],
        "maintenance_updates.csv": history[
            "maintenance_updates"
        ],
        "moveout_inspections.csv": history["inspections"],
        "deposit_settlements.csv": history["deposits"],
        "tenancy_events.csv": history["tenancy_events"],
        "activity_timeline.csv": _display_timeline(
            history["timeline"]
        ),
    }

    buffer = io.BytesIO()

    with zipfile.ZipFile(
        buffer,
        "w",
        zipfile.ZIP_DEFLATED,
    ) as archive:

        for name, rows in sections.items():

            if rows:
                archive.writestr(
                    name,
                    _csv_bytes(rows),
                )

        for settlement_id, rows in (
            history["deductions_by_settlement"].items()
        ):

            if rows:
                archive.writestr(
                    f"deposit_deductions_{settlement_id}.csv",
                    _csv_bytes(rows),
                )

    return buffer.getvalue()


# ==========================================================
# COLLAPSIBLE DETAIL SECTIONS
# ==========================================================

def _show_section(
    title: str,
    rows: list[dict],
    *,
    expanded=False,
) -> None:

    with st.expander(
        f"{title} ({len(rows)})",
        expanded=expanded,
    ):

        if rows:
            st.dataframe(
                rows,
                hide_index=True,
                use_container_width=True,
            )

        else:
            st.caption(
                "No records for this resident."
            )


# ==========================================================
# MAIN TENANT HISTORY INTERFACE
# ==========================================================

def render_admin_tenant_history(
    admin_id: int,
) -> None:

    # ----------------------------------------------
    # VERIFY ADMIN SESSION
    # ----------------------------------------------

    session = get_current_user() or {}

    if (
        str(session.get("role", "")).lower()
        != "admin"
    ):
        st.error(
            "Administrator access required."
        )
        return

    if (
        int(session.get("id", 0))
        != int(admin_id)
    ):
        st.error(
            "Administrator session mismatch."
        )
        return

    # ----------------------------------------------
    # PAGE HEADER
    # ----------------------------------------------

    st.subheader(
        "Unified Tenant History & Reporting"
    )

    st.caption(
        "Read-only resident records, including archived "
        "accounts. Downloads contain personal and "
        "financial information; handle securely."
    )

    # ----------------------------------------------
    # LOAD RESIDENT LIST
    # ----------------------------------------------

    try:

        residents = get_history_residents(
            admin_id
        )

    except PermissionError as exc:
        st.error(str(exc))
        return

    except Exception:
        logger.exception(
            "Could not load resident history selector"
        )

        st.error(
            "Unable to load tenant history."
        )
        return

    if not residents:

        st.info(
            "No resident records found."
        )

        return

    # ==================================================
    # SELECT RESIDENT
    # ==================================================

    resident_by_id = {
        row["id"]: row
        for row in residents
    }

    selected_id = st.selectbox(
        "Select resident (active or archived)",
        options=list(resident_by_id),
        format_func=lambda value: (
            f"{resident_by_id[value]['name']} "
            f"· {resident_by_id[value]['email']} "
            f"· "
            f"{'Active' if resident_by_id[value]['active'] else 'Archived'}"
        ),
        key="bm_tenant_history_resident_id",
    )

    # ----------------------------------------------
    # LOAD SELECTED RESIDENT HISTORY
    # ----------------------------------------------

    try:

        history = get_resident_history(
            admin_id,
            selected_id,
        )

    except (
        ValueError,
        PermissionError,
    ) as exc:

        st.error(str(exc))
        return

    except Exception:
        logger.exception(
            "Could not load resident history"
        )

        st.error(
            "Unable to load records for this resident."
        )
        return

    resident = history[
        "resident"
    ]

    summary = history[
        "summary"
    ]

    # ==================================================
    # RESIDENT PROFILE
    # ==================================================

    with st.container(
        border=True
    ):

        st.markdown(
            f"**{resident['name']}** "
            f"· {resident['status']}"
        )

        st.write(
            f"**Email:** {resident['email']}"
        )

        st.write(
            f"**Phone:** {resident['phone']}"
        )

        st.write(
            "**Current apartment:** "
            f"Unit {resident['current_unit']}"
        )

        st.write(
            f"**Resident ID:** {resident['id']}"
        )

    # ==================================================
    # OVERVIEW METRICS
    # ==================================================

    a, b, c, d = st.columns(4)

    a.metric(
        "Leases",
        summary["leases"],
    )

    b.metric(
        "Transfers",
        summary["transfers"],
    )

    c.metric(
        "Rent Payments",
        summary["payments"],
    )

    d.metric(
        "Maintenance",
        summary["maintenance"],
    )

    e, f, g = st.columns(3)

    e.metric(
        "Inspections",
        summary["inspections"],
    )

    f.metric(
        "Deposit Settlements",
        summary["settlements"],
    )

    g.metric(
        "Confirmed Payments Recorded",
        f"${summary['confirmed_payments']:,.2f}",
    )

    st.caption(
        "Confirmed payments represent recorded successful "
        "payment statuses, not an outstanding balance "
        "or a reconciliation against bank records."
    )

    st.divider()

    # ==================================================
    # CHRONOLOGICAL ACTIVITY TIMELINE
    # ==================================================

    st.markdown(
        "#### Chronological Activity Timeline"
    )

    timeline = history[
        "timeline"
    ]

    categories = sorted(
        {
            item["category"]
            for item in timeline
        }
    )

    left, right = st.columns(
        [1, 2]
    )

    with left:

        category = st.selectbox(
            "Event category",
            ["All"] + categories,
            key="bm_tenant_history_category",
        )

    with right:

        search = st.text_input(
            "Search activity",
            placeholder=(
                "Search events and details"
            ),
            key="bm_tenant_history_search",
        ).strip().casefold()

    # ----------------------------------------------
    # FILTER TIMELINE EVENTS
    # ----------------------------------------------

    filtered = [
        item
        for item in timeline
        if (
            category == "All"
            or item["category"] == category
        )
        and (
            not search
            or search in item["event"].casefold()
            or search in item["details"].casefold()
        )
    ]

    st.caption(
        f"Showing {len(filtered)} of "
        f"{len(timeline)} events · newest first"
    )

    displayed = _display_timeline(
        filtered
    )

    if displayed:

        st.dataframe(
            displayed,
            hide_index=True,
            use_container_width=True,
        )

    else:

        st.info(
            "No events match your filters."
        )

    # ==================================================
    # DOWNLOAD REPORTS
    # ==================================================

    c1, c2 = st.columns(2)

    with c1:

        st.download_button(
            "Download Filtered Activity CSV",
            data=_csv_bytes(
                displayed
            ),
            file_name=(
                f"tenant_{selected_id}_activity.csv"
            ),
            mime="text/csv",
            disabled=not displayed,
            use_container_width=True,
        )

    with c2:

        st.download_button(
            "Download Complete History (ZIP)",
            data=_full_report_zip(
                history
            ),
            file_name=(
                f"tenant_{selected_id}_history.zip"
            ),
            mime="application/zip",
            use_container_width=True,
        )

    st.divider()

    # ==================================================
    # DETAILED HISTORY
    # ==================================================

    st.markdown(
        "#### Detailed Records"
    )

    _show_section(
        "Lease History",
        history["leases"],
        expanded=True,
    )

    _show_section(
        "Lease Renewals",
        history["renewals"],
    )

    _show_section(
        "Apartment Transfers",
        history["transfers"],
    )

    _show_section(
        "Rent Payment History",
        history["payments"],
    )

    _show_section(
        "Maintenance Requests",
        history["maintenance"],
    )

    _show_section(
        "Maintenance Status Updates",
        history["maintenance_updates"],
    )

    _show_section(
        "Move-Out Inspections",
        history["inspections"],
    )

    _show_section(
        "Security Deposit Settlements",
        history["deposits"],
    )

    _show_section(
        "Tenancy & Archive Events",
        history["tenancy_events"],
    )

    # ==================================================
    # ITEMIZED SECURITY DEPOSIT DEDUCTIONS
    # ==================================================

    with st.expander(
        "Itemized Security Deposit Deductions"
    ):

        found = False

        for settlement_id, rows in (
            history["deductions_by_settlement"].items()
        ):

            if rows:

                found = True

                st.write(
                    f"**Settlement #{settlement_id}**"
                )

                st.dataframe(
                    rows,
                    hide_index=True,
                    use_container_width=True,
                )

        if not found:

            st.caption(
                "No itemized deductions recorded "
                "for this resident."
            )

    st.caption(
        "This page does not alter leases, apartment "
        "assignments, payments, inspections, "
        "or settlement records."
    )
