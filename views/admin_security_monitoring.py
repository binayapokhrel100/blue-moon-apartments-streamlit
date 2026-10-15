
"""Read-only security monitoring UI for Blue Moon Apartments.

Sprint 11B.7B.
Only the backend security service authorizes requests.
"""

from datetime import datetime

import streamlit as st

from services.admin_security_monitoring_service import (
    get_admin_security_dashboard,
)


SOURCE_OPTIONS = (
    "All sources",
    "Authentication",
    "Administrator audit",
    "Emergency recovery",
)


# ==========================================================
# TIME FORMATTING
# ==========================================================

def _format_utc(value: datetime | None) -> str:
    """Display timestamps in UTC."""

    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")

    return "—"


# ==========================================================
# SUPER ADMIN SECURITY MONITORING
# ==========================================================

def render_admin_security_monitoring(
    *,
    admin_id: int,
) -> None:
    """
    Display security monitoring information.

    Security:
    - Backend revalidates Super Admin authorization.
    - All information is read-only.
    - No automatic account locking or unlocking.
    - No audit deletion.
    - No reset-code issuance.
    """

    st.subheader("Security Monitoring")

    st.caption(
        "Read-only administrator security activity, "
        "current login lockouts, password recovery, "
        "and emergency recovery audits. "
        "All timestamps are UTC."
    )

    # ==================================================
    # DASHBOARD FILTERS
    # ==================================================

    controls_left, controls_middle, controls_right = (
        st.columns([2, 2, 1])
    )

    with controls_left:

        days = st.selectbox(
            "Reporting window",
            options=[1, 7, 14, 30],
            index=1,
            format_func=lambda value: (
                "Last 24 hours"
                if value == 1
                else f"Last {value} days"
            ),
            key="bm_security_monitor_days",
        )

    with controls_middle:

        limit = st.selectbox(
            "Maximum timeline entries",
            options=[25, 50, 100, 200],
            index=2,
            key="bm_security_monitor_limit",
        )

    with controls_right:

        st.write(" ")

        st.button(
            "Refresh",
            key="bm_security_monitor_refresh",
            help="Fetch a fresh snapshot from the database.",
            use_container_width=True,
        )

    # ==================================================
    # LOAD AUTHORIZED SECURITY SNAPSHOT
    # ==================================================

    try:

        data = get_admin_security_dashboard(
            admin_id,
            days=days,
            limit=limit,
        )

    except (PermissionError, ValueError) as exc:

        st.error(str(exc))
        return

    except Exception:

        # Avoid exposing raw database errors or internal
        # connection details to the administrator UI.

        st.error(
            "Security monitoring could not be loaded. "
            "Review the application server logs."
        )
        return

    metrics = data["metrics"]

    st.caption(
        "Snapshot generated: "
        + _format_utc(data["generated_at_utc"])
        + " UTC"
    )

    # ==================================================
    # SECURITY ACTIVITY METRICS
    # ==================================================

    st.markdown("#### Security Activity")

    first_row = st.columns(4)

    first_row[0].metric(
        "Failed Auth Events",
        metrics["failed_auth_events"],
    )

    first_row[1].metric(
        "Blocked Auth Events",
        metrics["blocked_auth_events"],
    )

    first_row[2].metric(
        "Reset Requests",
        metrics["password_reset_requests"],
    )

    first_row[3].metric(
        "Completed Resets",
        metrics["completed_password_resets"],
    )

    st.write("")

    second_row = st.columns(3)

    second_row[0].metric(
        "Manual Login Unlocks",
        metrics["manual_unlocks"],
    )

    second_row[1].metric(
        "Emergency Recoveries",
        metrics["emergency_resets"],
    )

    second_row[2].metric(
        "Currently Locked Accounts",
        metrics["active_admin_lockouts"],
    )

    st.caption(
        "Activity metrics use the selected reporting window. "
        "Current lockouts use the rolling 15-minute login window. "
        "Failed and blocked event counts may overlap. "
        "Counts cover linked administrator events, "
        "not every unknown login attempt."
    )

    # ==================================================
    # ACCOUNTS NEEDING REVIEW
    # ==================================================

    st.divider()

    st.markdown("#### Accounts Needing Review")

    flags = data.get(
        "account_flags",
        [],
    )

    if flags:

        flag_rows = [
            {
                "Administrator": item["email"],
                "User ID": item["user_id"],
                "Failed Attempts (15 min)": (
                    item["failed_attempts"]
                ),
                "Current Status": item["status"],
            }
            for item in flags
        ]

        st.dataframe(
            flag_rows,
            use_container_width=True,
            hide_index=True,
        )

        st.warning(
            "Elevated failed attempts or temporary "
            "lockouts were detected. Review the audit "
            "activity and verify the employee before "
            "performing any recovery action."
        )

    else:

        st.info(
            "No active administrators currently meet "
            "the three-failed-attempt review threshold."
        )

    st.caption(
        "A failure threshold is a signal to review, "
        "not proof of a malicious attack."
    )

    # ==================================================
    # SECURITY AUDIT TIMELINE
    # ==================================================

    st.divider()

    st.markdown("#### Recent Security Timeline")

    source = st.selectbox(
        "Event Source",
        SOURCE_OPTIONS,
        key="bm_security_monitor_source",
    )

    failure_only = st.checkbox(
        "Show only failed or blocked authentication events",
        value=False,
        key="bm_security_monitor_failures_only",
    )

    timeline = data.get(
        "timeline",
        [],
    )

    # --------------------------------------------------
    # FILTER BY EVENT SOURCE
    # --------------------------------------------------

    if source != "All sources":

        timeline = [
            item
            for item in timeline
            if item["source"] == source
        ]

    # --------------------------------------------------
    # FILTER FAILED / BLOCKED AUTHENTICATION
    # --------------------------------------------------

    if failure_only:

        timeline = [
            item
            for item in timeline
            if (
                item["source"] == "Authentication"
                and item["outcome"] == "Failed / blocked"
            )
        ]

    # --------------------------------------------------
    # DISPLAY EVENTS
    # --------------------------------------------------

    if not timeline:

        st.info(
            "No security events match the selected filters."
        )

    else:

        rows = [
            {
                "Time (UTC)": _format_utc(
                    item["time_utc"]
                ),
                "Source": item["source"],
                "Activity": item["activity"],
                "Outcome": item["outcome"],
                "Account": (
                    item["account"] or "—"
                ),
                "Actor ID": (
                    item["actor_user_id"]
                    if item["actor_user_id"] is not None
                    else "—"
                ),
                "Target ID": (
                    item["target_user_id"]
                    if item["target_user_id"] is not None
                    else "—"
                ),
                "Details": (
                    item["details"] or "—"
                ),
            }
            for item in timeline
        ]

        st.dataframe(
            rows,
            use_container_width=True,
            hide_index=True,
        )

    # ==================================================
    # SECURITY INFORMATION
    # ==================================================

    st.caption(
        "Timeline filters operate on the newest entries "
        "returned by the service. Filtering does not search "
        "older events beyond the selected entry limit."
    )

    st.info(
        "This monitoring dashboard is read-only. "
        "To manage administrator lockouts, use the "
        "Account Recovery tab. To issue a verified "
        "password-reset code, use the Password Reset tab."
    )
