
"""Resident lease page for Blue Moon Apartments."""

import html
from textwrap import dedent

import streamlit as st

from components.cards import metric_card
from components.header import render_header
from core.session import get_current_user
from services.lease_service import (
    get_current_lease,
    get_lease_history,
)


# ==========================================
# HELPER FUNCTIONS
# ==========================================

def _safe(value) -> str:
    """Escape values inserted into HTML."""
    return html.escape(
        str(value if value is not None else ""),
        quote=True,
    )


def _format_date(value) -> str:
    if value is None:
        return "N/A"

    return value.strftime(
        "%b %d, %Y"
    ).replace(" 0", " ")


def _format_bathrooms(value) -> str:
    if value is None:
        return "N/A"

    number = float(value)

    if number.is_integer():
        return str(int(number))

    return str(number)


def _money(value) -> str:
    if value is None:
        return "N/A"

    return f"${value:,.2f}"


# ==========================================
# LEASE HISTORY CARD
# ==========================================

def _render_history_row(item: dict) -> None:

    unit = _safe(
        item.get("unit_number") or "N/A"
    )

    start = _safe(
        _format_date(item.get("start_date"))
    )

    end = _safe(
        _format_date(item.get("end_date"))
    )

    rent = _safe(
        _money(item.get("monthly_rent"))
    )

    status = _safe(
        str(item.get("status") or "N/A").title()
    )

    st.html(
        dedent(
            f"""
            <div class="lease-history-row">
                <div>
                    <strong>
                        Apartment {unit}
                    </strong>
                    <span>
                        {start} – {end}
                    </span>
                </div>

                <div>
                    <strong>{rent}</strong>
                    <span>{status}</span>
                </div>
            </div>
            """
        ).strip()
    )


# ==========================================
# MAIN LEASE PAGE
# ==========================================

def render_lease() -> None:

    user = get_current_user() or {}

    user_id = user.get("id")

    if user_id is None:
        st.error(
            "Unable to identify the current resident."
        )
        return

    # ======================================
    # FETCH CURRENT LEASE
    # ======================================

    lease = get_current_lease(user_id)

    render_header("My Lease")

    st.html(
        dedent(
            """
            <h1 class="page-title">
                My Lease
            </h1>

            <p class="page-description">
                View your current lease details,
                apartment information and lease term.
            </p>
            """
        ).strip()
    )

    if lease is None:
        st.warning(
            "No active lease was found for your account."
        )
        return

    # ======================================
    # SUMMARY METRIC CARDS
    # ======================================

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        metric_card(
            "Apartment",
            str(lease.get("unit_number") or "N/A"),
            "Blue Moon Apartments",
        )

    with col2:
        metric_card(
            "Monthly Rent",
            _money(lease.get("monthly_rent")),
            "Current lease",
        )

    with col3:
        metric_card(
            "Security Deposit",
            _money(lease.get("security_deposit")),
            "On file",
        )

    with col4:
        metric_card(
            "Lease Status",
            str(
                lease.get("status") or "N/A"
            ).title(),
            (
                f"{lease.get('days_remaining', 0)} "
                "days remaining"
            ),
        )

    st.html(
        '<div style="height: 16px;"></div>'
    )

    # ======================================
    # PREPARE LEASE DETAILS
    # ======================================

    unit = _safe(
        lease.get("unit_number") or "N/A"
    )

    status = _safe(
        str(lease.get("status") or "N/A").title()
    )

    start = _safe(
        _format_date(lease.get("start_date"))
    )

    end = _safe(
        _format_date(lease.get("end_date"))
    )

    bedrooms = _safe(
        lease.get("bedrooms")
        if lease.get("bedrooms") is not None
        else "N/A"
    )

    bathrooms = _safe(
        _format_bathrooms(
            lease.get("bathrooms")
        )
    )

    rent = _safe(
        _money(lease.get("monthly_rent"))
    )

    deposit = _safe(
        _money(lease.get("security_deposit"))
    )

    left, right = st.columns([1.35, 1])

    # ======================================
    # CURRENT LEASE DETAILS
    # ======================================

    with left:

        st.html(
            dedent(
                f"""
                <div class="lease-card">

                    <div class="lease-card-heading">

                        <div>
                            <span class="lease-label">
                                CURRENT LEASE
                            </span>

                            <h3>
                                Apartment {unit}
                            </h3>
                        </div>

                        <span class="lease-status-active">
                            {status}
                        </span>

                    </div>

                    <div class="lease-detail-grid">

                        <div>
                            <span>Lease Start</span>
                            <strong>{start}</strong>
                        </div>

                        <div>
                            <span>Lease End</span>
                            <strong>{end}</strong>
                        </div>

                        <div>
                            <span>Bedrooms</span>
                            <strong>{bedrooms}</strong>
                        </div>

                        <div>
                            <span>Bathrooms</span>
                            <strong>{bathrooms}</strong>
                        </div>

                        <div>
                            <span>Monthly Rent</span>
                            <strong>{rent}</strong>
                        </div>

                        <div>
                            <span>Security Deposit</span>
                            <strong>{deposit}</strong>
                        </div>

                    </div>

                </div>
                """
            ).strip()
        )

    # ======================================
    # LEASE PROGRESS
    # ======================================

    with right:

        progress = max(
            0,
            min(
                100,
                int(lease.get("progress") or 0),
            ),
        )

        days_remaining = _safe(
            lease.get("days_remaining", 0)
        )

        st.html(
            dedent(
                f"""
                <div class="lease-progress-card">

                    <span class="lease-label">
                        LEASE TERM
                    </span>

                    <h3>
                        Lease Progress
                    </h3>

                    <div class="lease-progress-number">
                        {progress}%
                    </div>

                    <p>
                        Your current lease ends on
                        <strong>{end}</strong>.
                    </p>

                    <div class="lease-days-box">

                        <strong>
                            {days_remaining}
                        </strong>

                        <span>
                            days remaining
                        </span>

                    </div>

                </div>
                """
            ).strip()
        )

        st.progress(
            progress / 100
        )

    # ======================================
    # RESIDENT INFORMATION
    # ======================================

    st.html(
        '<div style="height: 16px;"></div>'
    )

    resident_name = _safe(
        user.get("full_name") or "Resident"
    )

    resident_email = _safe(
        user.get("email") or ""
    )

    st.html(
        dedent(
            f"""
            <div class="lease-card">

                <span class="lease-label">
                    RESIDENT
                </span>

                <h3>
                    Leaseholder Information
                </h3>

                <div class="lease-detail-grid">

                    <div>
                        <span>
                            Primary Resident
                        </span>
                        <strong>
                            {resident_name}
                        </strong>
                    </div>

                    <div>
                        <span>Email</span>
                        <strong>
                            {resident_email}
                        </strong>
                    </div>

                    <div>
                        <span>Apartment</span>
                        <strong>{unit}</strong>
                    </div>

                    <div>
                        <span>Resident Type</span>
                        <strong>
                            Primary Leaseholder
                        </strong>
                    </div>

                </div>

            </div>
            """
        ).strip()
    )

    # ======================================
    # LEASE HISTORY
    # ======================================

    st.html(
        '<div style="height: 16px;"></div>'
    )

    with st.expander("View Lease History"):

        history = get_lease_history(user_id)

        if not history:
            st.info(
                "No lease history is available."
            )

        else:
            for item in history:
                _render_history_row(item)
