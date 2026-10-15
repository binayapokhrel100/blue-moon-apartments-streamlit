
"""Sprint 09 — administrator payment reports (read-only)."""

import csv
import io
import logging
from decimal import Decimal

import streamlit as st

from core.session import get_current_user
from services.admin_operations_service import (
    get_admin_payments,
)


logger = logging.getLogger(__name__)


# ==================================================
# FORMAT MONEY
# ==================================================

def _money(value: object) -> str:
    return (
        f"${Decimal(str(value or 0)):,.2f}"
    )


# ==================================================
# CSV EXPORT
# ==================================================

def _csv_export(
    rows: list[dict],
) -> bytes:
    """Export the currently filtered payment records."""

    output = io.StringIO()

    columns = [
        "Resident",
        "Email",
        "Amount",
        "Payment month",
        "Method",
        "Status",
        "Confirmation",
        "Paid at (UTC)",
    ]

    writer = csv.DictWriter(
        output,
        fieldnames=columns,
    )

    writer.writeheader()

    # Protect spreadsheet programs against
    # formula injection in exported text.

    def safe(value: object) -> str:
        result = str(
            value if value is not None else ""
        )

        if result.lstrip().startswith(
            (
                "=",
                "+",
                "-",
                "@",
                "\t",
                "\r",
            )
        ):
            return "'" + result

        return result

    for row in rows:

        writer.writerow(
            {
                "Resident": safe(
                    row["resident"]
                ),
                "Email": safe(
                    row["email"]
                ),
                "Amount": (
                    f"{row['amount']:.2f}"
                ),
                "Payment month": (
                    row["month"].isoformat()
                    if row["month"]
                    else ""
                ),
                "Method": safe(
                    row["method"]
                ),
                "Status": safe(
                    row["status"]
                ),
                "Confirmation": safe(
                    row["confirmation"]
                ),
                "Paid at (UTC)": (
                    row["paid_at"].isoformat(
                        sep=" "
                    )
                    if row["paid_at"]
                    else ""
                ),
            }
        )

    return output.getvalue().encode(
        "utf-8-sig"
    )


# ==================================================
# ADMIN PAYMENTS PAGE
# ==================================================

def render_admin_payments() -> None:
    """Display administrator payment reports."""

    session = get_current_user() or {}

    role = str(
        session.get("role", "")
    ).strip().lower()

    if role != "admin":
        st.error(
            "Administrator access required."
        )
        st.stop()

    st.title(
        "Payment Management"
    )

    st.caption(
        "Review confirmed and pending payment "
        "records. This screen does not charge, "
        "refund, or edit payments."
    )

    # ------------------------------------------
    # LOAD DATA
    # ------------------------------------------

    try:

        data = get_admin_payments(
            int(session["id"])
        )

    except PermissionError:
        st.error(
            "Your administrator account "
            "is not authorized."
        )
        st.stop()

    except Exception:
        logger.exception(
            "Admin payments report could not load"
        )
        st.error(
            "Could not load payment records."
        )
        return

    # ------------------------------------------
    # PAYMENT SUMMARY
    # ------------------------------------------

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "All Payment Records",
        data["total_records"],
    )

    c2.metric(
        "Confirmed Payments",
        data["confirmed_records"],
    )

    c3.metric(
        "Confirmed Total",
        _money(
            data["confirmed_total"]
        ),
    )

    c4.metric(
        "Collected This Month",
        _money(
            data["collected_this_month"]
        ),
    )

    st.caption(
        f"Current month: {data['month_label']}. "
        "Collections use the actual paid date, "
        "not the billing month. Totals include "
        "all records; the table lists up to "
        "200 recent records."
    )

    # ------------------------------------------
    # SEARCH AND FILTER
    # ------------------------------------------

    records = data["payments"]

    search_col, status_col = st.columns(
        [2, 1]
    )

    with search_col:

        query = st.text_input(
            "Search payments",
            placeholder=(
                "Resident, email, confirmation "
                "number or method"
            ),
            key="admin_payment_search",
        ).strip().casefold()

    with status_col:

        statuses = [
            "All"
        ] + sorted(
            {
                str(record["status"])
                for record in records
            }
        )

        selected_status = st.selectbox(
            "Payment status",
            statuses,
            key="admin_payment_status",
        )

    # ------------------------------------------
    # FILTER RECORDS
    # ------------------------------------------

    filtered = []

    for record in records:

        haystack = " ".join(
            str(
                record[key] or ""
            )
            for key in (
                "resident",
                "email",
                "confirmation",
                "method",
            )
        ).casefold()

        if (
            query
            and query not in haystack
        ):
            continue

        if (
            selected_status != "All"
            and record["status"]
            != selected_status
        ):
            continue

        filtered.append(record)

    # ------------------------------------------
    # PAYMENT HISTORY
    # ------------------------------------------

    st.subheader(
        "Payment History"
    )

    st.caption(
        f"Showing {len(filtered)} of "
        f"{len(records)} recent records"
    )

    st.dataframe(
        [
            {
                "Resident": record["resident"],
                "Amount": _money(
                    record["amount"]
                ),
                "Billing Month": (
                    record["month"].strftime(
                        "%b %Y"
                    )
                    if record["month"]
                    else "—"
                ),
                "Payment Method": (
                    record["method"]
                ),
                "Status": (
                    record["status"]
                ),
                "Confirmation": (
                    record["confirmation"]
                ),
                "Paid At (UTC)": (
                    record["paid_at"].strftime(
                        "%b %d, %Y %I:%M %p"
                    )
                    if record["paid_at"]
                    else "—"
                ),
            }
            for record in filtered
        ],
        hide_index=True,
        use_container_width=True,
    )

    # ------------------------------------------
    # DOWNLOAD CSV
    # ------------------------------------------

    st.download_button(
        "Download filtered records (CSV)",
        data=_csv_export(filtered),
        file_name=(
            "blue_moon_payment_records.csv"
        ),
        mime="text/csv",
        key="admin_export_payments",
        disabled=not bool(filtered),
    )

    st.info(
        "This page is intentionally read-only. "
        "Recording payments or processing refunds "
        "requires a separate audited billing workflow."
    )
