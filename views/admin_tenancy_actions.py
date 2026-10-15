
"""Streamlit forms for Blue Moon tenancy termination and archiving."""

import logging

import streamlit as st
from sqlalchemy.exc import IntegrityError

from services.admin_tenancy_service import (
    archive_resident,
    get_active_tenancies,
    get_archive_candidates,
    get_tenancy_history,
    terminate_lease_and_move_out,
)


logger = logging.getLogger(__name__)


# ==========================================================
# SHARED SAVE HANDLER
# ==========================================================

def _execute_action(action, success_message: str) -> None:
    try:
        action()

    except (ValueError, PermissionError) as exc:
        st.error(str(exc))

    except IntegrityError:
        st.error(
            "The database rejected this change. "
            "Refresh the page and try again."
        )

    except Exception:
        logger.exception(
            "Admin tenancy action failed"
        )
        st.error(
            "Unable to complete the operation. "
            "No success has been confirmed."
        )

    else:
        st.session_state[
            "admin_tenant_flash"
        ] = success_message

        st.rerun()


# ==========================================================
# LEASE TERMINATION / MOVE-OUT
# ==========================================================

def render_lease_moveout(
    admin_id: int,
) -> None:
    """Manage immediate lease termination and resident move-out."""

    st.subheader(
        "Lease Termination / Move-Out"
    )

    st.caption(
        "End an active tenancy, archive the resident "
        "account, and release the apartment."
    )

    st.warning(
        "This action is effective immediately. "
        "It does not automatically issue refunds, "
        "settle outstanding balances, or determine "
        "contractual lease-break penalties."
    )

    try:
        tenancies = get_active_tenancies(
            admin_id
        )

    except PermissionError as exc:
        st.error(str(exc))
        return

    except Exception:
        logger.exception(
            "Cannot load active tenancies"
        )
        st.error(
            "Unable to load active leases."
        )
        return

    if not tenancies:
        st.info(
            "There are currently no active tenancies "
            "eligible for immediate move-out."
        )
        return

    options = {
        item["resident_id"]: item
        for item in tenancies
    }

    selected_id = st.selectbox(
        "Select tenant with an active lease",
        list(options),
        format_func=lambda user_id: (
            f"{options[user_id]['resident']} "
            f"· Unit {options[user_id]['unit']}"
        ),
        key="bm_terminate_tenant_selected",
    )

    item = options[selected_id]

    with st.container(border=True):
        st.markdown(
            f"**Resident:** {item['resident']}"
        )

        st.write(
            f"**Email:** {item['email']}"
        )

        st.write(
            f"**Apartment:** Unit {item['unit']}"
        )

        st.write(
            "**Lease period:** "
            f"{item['start_date']:%b %d, %Y} — "
            f"{item['end_date']:%b %d, %Y}"
        )

        st.write(
            "**Monthly rent:** "
            f"${item['monthly_rent']:,.2f}"
        )

        st.write(
            "**Recorded security deposit:** "
            f"${item['security_deposit']:,.2f}"
        )

    st.markdown("#### Complete Move-Out")

    with st.form(
        f"bm_lease_moveout_form_{selected_id}"
    ):
        reason = st.text_area(
            "Reason for lease termination *",
            placeholder=(
                "Example: Resident requested early "
                "termination and returned keys."
            ),
            max_chars=2000,
            height=120,
        )

        st.caption(
            "Effective date: Today. The original "
            "contractual end date will remain in "
            "the lease history."
        )

        confirmed = st.checkbox(
            "I confirm that move-out is effective "
            "today and this tenant's login should "
            "be deactivated."
        )

        submitted = st.form_submit_button(
            "Terminate Lease & Complete Move-Out",
            type="primary",
        )

    if submitted:
        if not confirmed:
            st.error(
                "Please confirm the move-out "
                "before continuing."
            )

        else:
            _execute_action(
                lambda: terminate_lease_and_move_out(
                    admin_id,
                    selected_id,
                    reason=reason,
                ),
                "Lease terminated and move-out recorded. "
                "The tenant account has been archived.",
            )


# ==========================================================
# REMOVE / ARCHIVE TENANT
# ==========================================================

def render_archive_tenant(
    admin_id: int,
) -> None:
    """Archive a resident account without an active lease."""

    st.subheader(
        "Remove / Archive Tenant"
    )

    st.caption(
        "Remove a tenant from active accounts "
        "while preserving their database history."
    )

    st.info(
        "Archive is the safe form of tenant removal. "
        "The resident will no longer be able to log in, "
        "and their apartment assignment will be cleared. "
        "Historical leases, payments, maintenance requests, "
        "and notifications will not be deleted."
    )

    try:
        candidates = get_archive_candidates(
            admin_id
        )

    except PermissionError as exc:
        st.error(str(exc))
        return

    except Exception:
        logger.exception(
            "Cannot load archive candidates"
        )
        st.error(
            "Unable to load tenants eligible for archiving."
        )
        return

    if candidates:
        by_id = {
            person["resident_id"]: person
            for person in candidates
        }

        selected_id = st.selectbox(
            "Select tenant to remove from active accounts",
            list(by_id),
            format_func=lambda uid: (
                f"{by_id[uid]['name']} "
                f"· {by_id[uid]['email']}"
            ),
            key="bm_archive_tenant_selected",
        )

        selected = by_id[
            selected_id
        ]

        with st.container(border=True):
            st.write(
                f"**Resident:** {selected['name']}"
            )
            st.write(
                f"**Email:** {selected['email']}"
            )
            st.write(
                f"**Current assignment:** "
                f"{selected['unit']}"
            )
            st.write(
                "**Active lease:** No"
            )

        with st.form(
            f"bm_archive_tenant_form_{selected_id}"
        ):
            reason = st.text_area(
                "Reason for removing this tenant *",
                placeholder=(
                    "Example: Account no longer required "
                    "after move-out."
                ),
                max_chars=2000,
                height=110,
            )

            confirmed = st.checkbox(
                "I understand this will disable the "
                "resident account and clear its "
                "apartment assignment."
            )

            submitted = st.form_submit_button(
                "Archive Tenant Account",
                type="primary",
            )

        if submitted:
            if not confirmed:
                st.error(
                    "Please confirm that you want "
                    "to archive this resident."
                )

            else:
                _execute_action(
                    lambda: archive_resident(
                        admin_id,
                        selected_id,
                        reason=reason,
                    ),
                    "Resident archived successfully. "
                    "Historical records are preserved.",
                )

    else:
        st.info(
            "No active resident accounts are eligible "
            "for archiving. A tenant with an active "
            "lease must complete the move-out workflow first."
        )

    # ------------------------------------------
    # TENANCY AUDIT HISTORY
    # ------------------------------------------

    st.divider()
    st.subheader(
        "Recent Tenancy Activity"
    )

    try:
        history = get_tenancy_history(
            admin_id
        )

    except PermissionError as exc:
        st.error(str(exc))
        return

    except Exception:
        logger.exception(
            "Cannot load tenancy audit history"
        )
        st.error(
            "Could not load tenancy history."
        )
        return

    if not history:
        st.caption(
            "No lease terminations or tenant "
            "archives have been recorded yet."
        )
        return

    st.dataframe(
        [
            {
                "Date": row["date"],
                "Tenant": row["resident"],
                "Apartment": row["apartment"],
                "Action": (
                    "Lease Terminated"
                    if row["action"] == "lease_terminated"
                    else "Account Archived"
                ),
                "Reason": row["reason"],
                "Original Lease End": (
                    row["original_lease_end"]
                    or "—"
                ),
                "Admin ID": row["admin_id"],
            }
            for row in history
        ],
        hide_index=True,
        use_container_width=True,
    )
