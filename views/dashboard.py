
"""Blue Moon Apartments — redesigned resident dashboard."""

from datetime import date, datetime
from decimal import Decimal
import html
from pathlib import Path
import streamlit as st
from sqlalchemy import func, or_, select

from components.header import render_header
from core.session import get_current_user
from database.db import get_db_session
from database.models import (
    Announcement,
    Apartment,
    Lease,
    MaintenanceRequest,
    Notification,
    Payment,
    User,
)

def load_dashboard_css():
    css_path = (
        Path(__file__).resolve().parent.parent
        / "styles"
        / "dashboard.css"
    )

    css = css_path.read_text(encoding="utf-8")
    st.html(f"<style>{css}</style>")



# ==================================================
# HELPER FUNCTIONS
# ==================================================

def _escape(value) -> str:
    return html.escape(
        str(value if value is not None else ""),
        quote=True,
    )


def _money(value) -> str:
    if value is None:
        return "Not available"

    return f"${Decimal(str(value)):,.2f}"


def _date(value) -> str:
    if not value:
        return "Not recorded"

    if isinstance(value, (date, datetime)):
        return value.strftime(
            "%b %d, %Y"
        ).replace(" 0", " ")

    return str(value)


def _navigate(
    page: str,
    question: str | None = None,
) -> None:

    if question:
        st.session_state[
            "assistant_pending_question"
        ] = question

    st.session_state.current_page = page

    st.rerun()


# ==================================================
# LOAD DATABASE INFORMATION
# ==================================================

def _load_dashboard(user_id: int) -> dict:

    now = datetime.utcnow()

    completed_statuses = (
        "completed",
        "resolved",
        "closed",
        "cancelled",
        "canceled",
    )

    with get_db_session() as db:

        # ======================================
        # CURRENT RESIDENT
        # ======================================

        user = db.scalar(
            select(User).where(
                User.id == user_id
            )
        )

        if (
            user is None
            or user.role != "resident"
            or not user.is_active
        ):
            raise PermissionError(
                "An active resident account is required."
            )

        # ======================================
        # APARTMENT
        # ======================================

        apartment = (
            db.get(
                Apartment,
                user.apartment_id,
            )
            if user.apartment_id is not None
            else None
        )

        # ======================================
        # ACTIVE LEASE
        # ======================================

        lease = db.scalar(
            select(Lease)
            .where(
                Lease.resident_id == user_id,
                Lease.status == "active",
            )
            .order_by(
                Lease.start_date.desc()
            )
            .limit(1)
        )

        # ======================================
        # RECENT PAYMENTS
        # ======================================

        payments = db.scalars(
            select(Payment)
            .where(
                Payment.resident_id == user_id
            )
            .order_by(
                Payment.paid_at.desc(),
                Payment.id.desc(),
            )
            .limit(3)
        ).all()

        # ======================================
        # OPEN MAINTENANCE
        # ======================================

        open_requests = db.scalars(
            select(MaintenanceRequest)
            .where(
                MaintenanceRequest.resident_id == user_id,
                func.lower(
                    MaintenanceRequest.status
                ).notin_(
                    completed_statuses
                ),
            )
            .order_by(
                MaintenanceRequest.created_at.desc()
            )
            .limit(3)
        ).all()

        open_count = db.scalar(
            select(
                func.count(
                    MaintenanceRequest.id
                )
            )
            .where(
                MaintenanceRequest.resident_id == user_id,
                func.lower(
                    MaintenanceRequest.status
                ).notin_(
                    completed_statuses
                ),
            )
        ) or 0

        # ======================================
        # CURRENT ANNOUNCEMENTS
        # ======================================

        notice_filter = (
            Announcement.is_published.is_(True),
            or_(
                Announcement.published_at.is_(None),
                Announcement.published_at <= now,
            ),
            or_(
                Announcement.expires_at.is_(None),
                Announcement.expires_at >= now,
            ),
        )

        announcements = db.scalars(
            select(Announcement)
            .where(*notice_filter)
            .order_by(
                Announcement.published_at.desc()
            )
            .limit(3)
        ).all()

        announcement_count = db.scalar(
            select(
                func.count(
                    Announcement.id
                )
            ).where(*notice_filter)
        ) or 0

        # ======================================
        # UNREAD NOTIFICATIONS
        # ======================================

        unread_count = db.scalar(
            select(
                func.count(
                    Notification.id
                )
            )
            .where(
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
            )
        ) or 0

        # ======================================
        # CONFIRMED PAYMENT COUNT
        # ======================================

        confirmed_count = db.scalar(
            select(
                func.count(
                    Payment.id
                )
            )
            .where(
                Payment.resident_id == user_id,
                func.lower(
                    Payment.status
                ).in_(
                    (
                        "confirmed",
                        "paid",
                        "completed",
                    )
                ),
            )
        ) or 0

        # ======================================
        # RETURN DISPLAY DATA
        # ======================================

        return {
            "full_name": (
                user.full_name
                or user.first_name
                or "Resident"
            ),
            "unit": (
                apartment.unit_number
                if apartment
                else "Not assigned"
            ),
            "monthly_rent": (
                lease.monthly_rent
                if lease
                else None
            ),
            "lease_end": (
                lease.end_date
                if lease
                else None
            ),
            "lease_status": (
                lease.status
                if lease
                else "No active lease"
            ),
            "confirmed_count": confirmed_count,
            "open_count": open_count,
            "announcement_count": announcement_count,
            "unread_count": unread_count,
            "payments": [
                {
                    "amount": p.amount,
                    "paid_at": p.paid_at,
                    "status": p.status,
                }
                for p in payments
            ],
            "open_requests": [
                {
                    "description": m.description,
                    "category": m.category,
                    "location": m.location_detail,
                    "status": m.status,
                }
                for m in open_requests
            ],
            "announcements": [
                {
                    "title": a.title,
                    "published_at": a.published_at,
                    "priority": a.priority,
                }
                for a in announcements
            ],
        }


# ==================================================
# FOUR QUICK SUMMARY CARDS
# ==================================================

def _render_quick_stats(data: dict) -> None:

    last = (
        data["payments"][0]
        if data["payments"]
        else None
    )

    tiles = [
        (
            "✓",
            "bm8-green",
            "Last Payment",
            (
                _money(last["amount"])
                if last
                else "None"
            ),
            (
                _date(last["paid_at"])
                if last
                else "No recorded payments"
            ),
        ),
        (
            "⚒",
            "bm8-blue",
            "Open Requests",
            str(data["open_count"]),
            "Maintenance requests",
        ),
        (
            "!",
            "bm8-yellow",
            "Announcements",
            str(data["announcement_count"]),
            "Current published notices",
        ),
        (
            "♧",
            "bm8-sky",
            "Notifications",
            str(data["unread_count"]),
            "Unread messages",
        ),
    ]

    cards = "".join(
        (
            f'<div class="bm8-quick">'
            f'<div class="bm8-quick-icon {icon_class}">'
            f'{_escape(icon)}'
            f'</div>'
            f'<small>{_escape(label)}</small>'
            f'<strong>{_escape(value)}</strong>'
            f'<span>{_escape(note)}</span>'
            f'</div>'
        )
        for icon, icon_class, label, value, note in tiles
    )

    st.html(
        f'<div class="bm8-quick-grid">{cards}</div>'
    )


# ==================================================
# MAIN RESIDENT DASHBOARD
# ==================================================

def render_dashboard() -> None:

    session = get_current_user() or {}

    user_id = session.get("id")

    if not user_id:
        st.error(
            "Please sign in to view your dashboard."
        )
        return

    try:
        data = _load_dashboard(user_id)

    except PermissionError:
        st.error(
            "This dashboard is available "
            "to active residents only."
        )
        return

    # ======================================
    # LOAD STYLES AND HEADER
    # ======================================

    load_dashboard_css()

    render_header("Dashboard")

    with st.container(key="bm8_page"):

        # ==================================
        # NAVY WELCOME BANNER
        # ==================================

        with st.container(key="bm8_hero"):

            hour = datetime.now().hour

            greeting = (
                "GOOD MORNING"
                if hour < 12
                else (
                    "GOOD AFTERNOON"
                    if hour < 18
                    else "GOOD EVENING"
                )
            )

            st.html(
                f"""
                <div class="bm8-hero">

                    <div class="bm8-eyebrow">
                        {greeting}
                    </div>

                    <div class="bm8-hero-name">
                        {_escape(data['full_name'])}
                    </div>

                    <div class="bm8-pills">

                        <span class="bm8-pill">
                            ⌂ &nbsp; Apt {_escape(data['unit'])}
                            · Blue Moon
                        </span>

                        <span class="bm8-pill bm8-pill-green">
                            ✓ Resident account
                        </span>

                    </div>

                    <div class="bm8-hero-grid">

                        <div class="bm8-hero-stat">
                            <small>Monthly rent</small>
                            <strong>
                                {_escape(_money(data['monthly_rent']))}
                            </strong>
                            <span>As listed on your lease</span>
                        </div>

                        <div class="bm8-hero-stat">
                            <small>Lease ends</small>
                            <strong>
                                {_escape(_date(data['lease_end']))}
                            </strong>
                            <span>View your lease for details</span>
                        </div>

                        <div class="bm8-hero-stat">
                            <small>Payments recorded</small>
                            <strong>
                                {data['confirmed_count']}
                            </strong>
                            <span>Confirmed payment records</span>
                        </div>

                    </div>

                </div>
                """
            )

            make_col, view_col = st.columns(
                [3, 1],
                gap="small",
            )

            with make_col:

                if st.button(
                    "▣  Make Payment",
                    key="bm8_make_payment",
                    type="primary",
                    use_container_width=True,
                ):
                    _navigate("payments")

            with view_col:

                if st.button(
                    "View Charges",
                    key="bm8_view_charges",
                    use_container_width=True,
                ):
                    _navigate("payments")

        # ==================================
        # FOUR SUMMARY CARDS
        # ==================================

        _render_quick_stats(data)

        # ==================================
        # TWO-COLUMN MAIN CONTENT
        # ==================================

        left, right = st.columns(
            [1.48, 1],
            gap="medium",
        )

        # ==================================
        # LEFT COLUMN
        # ==================================

        with left:

            # ------------------------------
            # ACTIVE MAINTENANCE
            # ------------------------------

            with st.container(
                key="bm8_maintenance"
            ):

                st.html(
                    """
                    <div class="bm8-heading">
                        <span class="bm8-heading-icon">⚒</span>
                        Active Maintenance
                    </div>
                    """
                )

                if data["open_requests"]:

                    rows = "".join(
                        (
                            '<div class="bm8-row">'
                            '<div class="bm8-row-text">'
                            f'<strong>'
                            f'{_escape(item["description"] or item["category"] or "Maintenance request")}'
                            f'</strong>'
                            f'<span>'
                            f'{_escape(item["category"] or "Maintenance")}'
                            f' · '
                            f'{_escape(item["location"] or "Apartment")}'
                            f'</span>'
                            '</div>'
                            '<span class="bm8-tag">'
                            f'{_escape(item["status"] or "Open")}'
                            '</span>'
                            '</div>'
                        )
                        for item in data["open_requests"][:2]
                    )

                    st.html(rows)

                else:

                    st.html(
                        """
                        <p class="bm8-empty">
                            No open maintenance requests.
                        </p>
                        """
                    )

                if st.button(
                    "＋ Submit Maintenance Request",
                    key="bm8_new_request",
                    type="primary",
                    use_container_width=True,
                ):
                    _navigate("maintenance")

            # ------------------------------
            # RECENT PAYMENTS
            # ------------------------------

            with st.container(
                key="bm8_payments"
            ):

                st.html(
                    """
                    <div class="bm8-heading">
                        <span class="bm8-heading-icon">▣</span>
                        Recent Payments
                    </div>
                    """
                )

                if data["payments"]:

                    rows = ""

                    for payment in data["payments"]:

                        status = str(
                            payment["status"]
                            or "Unknown"
                        )

                        cls = (
                            "bm8-tag bm8-tag-good"
                            if status.casefold() in (
                                "paid",
                                "confirmed",
                                "completed",
                            )
                            else "bm8-tag bm8-tag-warn"
                        )

                        rows += (
                            '<div class="bm8-row">'
                            '<div class="bm8-row-text">'
                            f'<strong>'
                            f'{_escape(_money(payment["amount"]))}'
                            f'</strong>'
                            f'<span>'
                            f'{_escape(_date(payment["paid_at"]))}'
                            f'</span>'
                            '</div>'
                            f'<span class="{cls}">'
                            f'{_escape(status.title())}'
                            '</span>'
                            '</div>'
                        )

                    st.html(rows)

                else:

                    st.html(
                        """
                        <p class="bm8-empty">
                            No recorded payments yet.
                        </p>
                        """
                    )

                if st.button(
                    "View Payment History →",
                    key="bm8_payment_history",
                ):
                    _navigate("payments")

        # ==================================
        # RIGHT COLUMN
        # ==================================

        with right:

            # ------------------------------
            # BLUE MOON ASSISTANT
            # ------------------------------

            with st.container(
                key="bm8_assistant"
            ):

                st.html(
                    """
                    <div class="bm8-assistant-title">
                        ☾ &nbsp; Blue Moon Assistant
                    </div>

                    <p class="bm8-assistant-detail">
                        Ask about your rent, maintenance,
                        or apartment information.
                    </p>

                    <div class="bm8-assistant-status">
                        ● Offline · Ready to help
                    </div>
                    """
                )

                if st.button(
                    "How much is my monthly rent?",
                    key="bm8_rent_question",
                    use_container_width=True,
                ):
                    _navigate(
                        "assistant",
                        "What is my monthly rent?",
                    )

                if st.button(
                    "Check maintenance status",
                    key="bm8_maintenance_question",
                    use_container_width=True,
                ):
                    _navigate(
                        "assistant",
                        "What is my maintenance status?",
                    )

            # ------------------------------
            # ANNOUNCEMENTS
            # ------------------------------

            with st.container(
                key="bm8_announcements"
            ):

                st.html(
                    """
                    <div class="bm8-heading">
                        <span class="bm8-heading-icon">!</span>
                        Announcements
                    </div>
                    """
                )

                if data["announcements"]:

                    rows = ""

                    for item in data["announcements"]:

                        priority = str(
                            item["priority"]
                            or "Normal"
                        )

                        cls = (
                            "bm8-tag bm8-tag-warn"
                            if priority.lower() == "important"
                            else "bm8-tag"
                        )

                        rows += (
                            '<div class="bm8-row">'
                            '<div class="bm8-row-text">'
                            f'<strong>{_escape(item["title"])}</strong>'
                            f'<span>{_escape(_date(item["published_at"]))}</span>'
                            '</div>'
                            f'<span class="{cls}">'
                            f'{_escape(priority)}'
                            '</span>'
                            '</div>'
                        )

                    st.html(rows)

                else:

                    st.html(
                        """
                        <p class="bm8-empty">
                            No current announcements.
                        </p>
                        """
                    )

                if st.button(
                    "View All Announcements →",
                    key="bm8_announcements_all",
                ):
                    _navigate("announcements")

            # ------------------------------
            # LEASE OVERVIEW
            # ------------------------------

            with st.container(
                key="bm8_lease"
            ):

                st.html(
                    f"""
                    <div class="bm8-lease-title">
                        LEASE OVERVIEW
                    </div>

                    <div class="bm8-lease-row">
                        <span>Unit</span>
                        <strong>
                            {_escape(data['unit'])}
                        </strong>
                    </div>

                    <div class="bm8-lease-row">
                        <span>Lease End</span>
                        <strong>
                            {_escape(_date(data['lease_end']))}
                        </strong>
                    </div>

                    <div class="bm8-lease-row">
                        <span>Status</span>
                        <strong>
                            {_escape(str(data['lease_status']).title())}
                        </strong>
                    </div>
                    """
                )

                if st.button(
                    "View My Lease →",
                    key="bm8_lease_details",
                ):
                    _navigate("lease")
