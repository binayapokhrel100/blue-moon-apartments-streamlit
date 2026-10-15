
"""Blue Moon Apartments — Sprint 09 admin overview."""

import logging
from datetime import datetime
from decimal import Decimal
from html import escape
from pathlib import Path

import streamlit as st

from core.session import get_current_user, logout_user
from services.admin_dashboard_service import get_admin_dashboard_data

logger = logging.getLogger(__name__)


def _load_admin_css() -> None:
    """Load admin-only styles without changing main.css or dashboard.css."""
    path = Path(__file__).resolve().parent.parent / "styles" / "admin.css"
    css = path.read_text(encoding="utf-8")
    st.html(f"<style>{css}</style>")


def _text(value: object) -> str:
    return escape(str(value) if value is not None else "—", quote=True)


def _date(value: datetime | None) -> str:
    return value.strftime("%b %d, %Y") if value else "—"


def _money(value: object) -> str:
    return f"${Decimal(str(value or 0)):,.2f}"


def _metric(label: str, value: str, detail: str, accent: str) -> str:
    return f"""
    <div class="bm-admin-metric {accent}">
        <span class="bm-admin-metric-label">{_text(label)}</span>
        <strong>{_text(value)}</strong>
        <small>{_text(detail)}</small>
    </div>
    """


def _maintenance_panel(items: list[dict]) -> str:
    rows = []
    for item in items:
        status = str(item["status"] or "Unknown")
        normalized = status.strip().lower()
        badge_class = (
            "done" if normalized == "completed"
            else "pending" if normalized in {"submitted", "scheduled"}
            else "active" if normalized == "in progress"
            else "neutral"
        )
        rows.append(f"""
            <div class="bm-admin-list-row">
                <div class="bm-admin-list-copy">
                    <strong>{_text(item['category'])}</strong>
                    <span>{_text(item['request_number'])} · Unit {_text(item['unit'])} · {_text(item['resident'])}</span>
                    <small>{_text(_date(item['created_at']))} · {_text(item['urgency'])} priority</small>
                </div>
                <span class="bm-admin-badge {badge_class}">{_text(status)}</span>
            </div>
        """)

    content = "".join(rows) if rows else '<p class="bm-admin-empty">No maintenance requests yet.</p>'
    return f"""
        <div class="bm-admin-panel">
            <div class="bm-admin-panel-heading">
                <div><h3>Maintenance Requests</h3><p>Most recently submitted requests</p></div>
                <span class="bm-admin-mini-icon">🔧</span>
            </div>
            {content}
        </div>
    """


def _payments_panel(items: list[dict]) -> str:
    rows = []
    for item in items:
        status = str(item["status"] or "Unknown")
        badge_class = "done" if status.lower() == "confirmed" else "neutral"
        rows.append(f"""
            <div class="bm-admin-list-row">
                <div class="bm-admin-list-copy">
                    <strong>{_text(item['resident'])}</strong>
                    <span>{_text(item['method'])}</span>
                    <small>{_text(_date(item['paid_at']))}</small>
                </div>
                <div class="bm-admin-payment-end">
                    <strong>{_text(_money(item['amount']))}</strong>
                    <span class="bm-admin-badge {badge_class}">{_text(status)}</span>
                </div>
            </div>
        """)

    content = "".join(rows) if rows else '<p class="bm-admin-empty">No payments recorded yet.</p>'
    return f"""
        <div class="bm-admin-panel">
            <div class="bm-admin-panel-heading">
                <div><h3>Recent Payments</h3><p>Latest payment records in the system</p></div>
                <span class="bm-admin-mini-icon">💳</span>
            </div>
            {content}
        </div>
    """


def _announcements_panel(items: list[dict]) -> str:
    rows = []
    for item in items:
        rows.append(f"""
            <div class="bm-admin-list-row">
                <div class="bm-admin-list-copy">
                    <strong>{_text(item['title'])}</strong>
                    <span>{_text(item['category'])}</span>
                    <small>Published {_text(_date(item['published_at']))}</small>
                </div>
            </div>
        """)
    content = "".join(rows) if rows else '<p class="bm-admin-empty">No currently published announcements.</p>'
    return f"""
        <div class="bm-admin-panel">
            <div class="bm-admin-panel-heading">
                <div><h3>Community Announcements</h3><p>Published and unexpired notices</p></div>
                <span class="bm-admin-mini-icon">📣</span>
            </div>
            {content}
        </div>
    """


def _occupancy_panel(data: dict) -> str:
    rate = float(data["occupancy_rate"])
    safe_width = max(0.0, min(100.0, rate))
    return f"""
        <div class="bm-admin-panel bm-admin-occupancy">
            <div class="bm-admin-panel-heading">
                <div><h3>Apartment Occupancy</h3><p>Current unit availability</p></div>
                <span class="bm-admin-mini-icon">🏢</span>
            </div>
            <div class="bm-admin-occupancy-number">{rate:.1f}%</div>
            <div class="bm-admin-progress" role="progressbar" aria-valuenow="{rate:.1f}" aria-valuemin="0" aria-valuemax="100" aria-label="Apartment occupancy">
                <div style="width:{safe_width:.1f}%"></div>
            </div>
            <div class="bm-admin-occupancy-details">
                <span><b>{int(data['occupied_units'])}</b> occupied</span>
                <span><b>{int(data['vacant_units'])}</b> vacant</span>
            </div>
        </div>
    """


def render_admin_dashboard() -> None:
    """Render a read-only dashboard for signed-in administrators."""

    session = get_current_user() or {}
    if str(session.get("role", "")).strip().lower() != "admin":
        st.error("Administrator access is required.")
        st.stop()

    _load_admin_css()

    try:
        data = get_admin_dashboard_data(int(session["id"]))
    except Exception:
        logger.exception("Unable to load admin dashboard")
        st.error("The admin dashboard could not load. Please try again.")
        return

    with st.container(key="bm_admin_page"):
        with st.container(key="bm_admin_header"):
            heading_col, action_col = st.columns([4, 1], gap="medium", vertical_alignment="center")
            with heading_col:
                st.html(f"""
                    <div class="bm-admin-eyebrow">BLUE MOON APARTMENTS · MANAGEMENT</div>
                    <h1 class="bm-admin-title">Property Overview</h1>
                    <p class="bm-admin-subtitle">Welcome, {_text(session.get('first_name') or 'Administrator')}.
                       Here's what's happening across the community.</p>
                """)
            with action_col:
                if st.button("↻ Refresh", key="bm_admin_refresh", use_container_width=True):
                    st.rerun()
                if st.button("Sign Out", key="bm_admin_logout", use_container_width=True):
                    logout_user()
                    st.session_state["bm_auth_screen"] = "selection"
                    st.rerun()

        st.html(f'<div class="bm-admin-section-heading">Overview <span>Updated {_text(data["updated_at"].strftime("%b %d, %Y · %I:%M %p"))} UTC</span></div>')

        metrics = [
            ("Total Apartments", str(data["total_apartments"]), "Units in the property", "blue"),
            ("Occupied Units", str(data["occupied_units"]), f'{data["occupancy_rate"]:.1f}% occupancy', "green"),
            ("Active Residents", str(data["active_residents"]), "Active resident accounts", "blue"),
            ("Open Maintenance", str(data["open_maintenance"]), "Not completed or cancelled", "amber"),
            ("Collected This Month", _money(data["monthly_collected"]), data["month_label"] + " · confirmed payments", "green"),
            ("Published Notices", str(data["published_notices"]), "Currently visible announcements", "blue"),
        ]

        for offset in (0, 3):
            columns = st.columns(3, gap="medium")
            for col, (label, value, detail, accent) in zip(columns, metrics[offset: offset + 3]):
                with col:
                    st.html(_metric(label, value, detail, accent))

        st.html('<div class="bm-admin-section-heading">Operations <span>Live database records</span></div>')
        left, right = st.columns([1.45, 1], gap="medium")
        with left:
            st.html(_maintenance_panel(data["maintenance"]))
        with right:
            st.html(_occupancy_panel(data))
            st.html(_announcements_panel(data["announcements"]))

        st.html(_payments_panel(data["payments"]))
        st.html('<p class="bm-admin-footnote">Sprint 09 · Read-only admin overview. Tenant management, maintenance updates and publishing controls will be added in subsequent stages.</p>')
