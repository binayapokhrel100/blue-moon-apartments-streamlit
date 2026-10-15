
"""
Blue Moon Apartments
Admin Security Deposit Settlement Interface

Features:
- Create deposit settlement drafts
- Add and remove itemized deductions
- Display estimated and approved refundable amounts
- Approve security deposit settlements
- Record externally completed refunds
- Close zero-refund settlements
- View settlement and audit history

IMPORTANT:
This application records refunds but does not transfer money.
"""

import logging
from datetime import date
from decimal import Decimal

import streamlit as st
from sqlalchemy.exc import IntegrityError

from core.session import get_current_user
from services.admin_rbac_service import get_my_admin_access

from services.admin_deposit_settlement_service import (
    DEDUCTION_CATEGORIES,
    REFUND_METHODS,
    add_deposit_deduction,
    approve_deposit_settlement,
    close_zero_refund_settlement,
    create_deposit_settlement,
    get_deposit_settlements,
    get_eligible_deposit_leases,
    record_external_refund,
    remove_deposit_deduction,
)


logger = logging.getLogger(__name__)


# ==========================================================
# CURRENCY FORMATTING
# ==========================================================

def _usd(value) -> str:
    """Format a decimal value as USD."""
    return f"${Decimal(str(value)):,.2f}"


# ==========================================================
# ADMIN ACTION HANDLER
# ==========================================================

def _perform(
    action,
    success_message: str,
    *,
    select_created: bool = False,
) -> None:
    """
    Execute an admin action safely.

    Refresh the page only after successful execution.
    """

    try:
        result = action()

    except (ValueError, PermissionError) as exc:
        st.error(str(exc))
        return

    except IntegrityError:
        st.error(
            "The database rejected this change. "
            "Refresh the page and try again."
        )
        return

    except Exception:
        logger.exception(
            "Security deposit settlement action failed"
        )

        st.error(
            "Unable to complete this action. "
            "Check the application logs."
        )
        return

    if select_created:
        st.session_state[
            "bm_deposit_selected_id"
        ] = result

    st.session_state[
        "bm_deposit_message"
    ] = success_message

    st.rerun()


# ==========================================================
# MAIN ADMIN SECURITY DEPOSIT SETTLEMENT PAGE
# ==========================================================

def render_admin_deposit_settlements(
    admin_id: int,
) -> None:

    # Confirm this view is operating on the signed-in administrator.
    session = get_current_user() or {}
    if (
        str(session.get("role") or "").strip().lower() != "admin"
        or str(session.get("id") or "") != str(admin_id)
    ):
        st.error("Administrator session mismatch. Please sign in again.")
        return

    # Fresh database-backed permissions, not permissions stored in session.
    try:
        access = get_my_admin_access(int(admin_id))
    except (PermissionError, ValueError) as exc:
        st.error(str(exc))
        return

    permissions = set(access["permissions"])
    if "deposits.read" not in permissions:
        st.error("You do not have permission to view deposit settlements.")
        return

    can_edit = "deposits.edit" in permissions
    can_approve = "deposits.approve" in permissions
    can_refund = "refunds.record" in permissions

    if not any((can_edit, can_approve, can_refund)):
        st.info("Security deposit settlements are read-only for your role.")

    st.subheader(
        "Security Deposit Settlement"
    )

    st.caption(
        "Review security deposits after lease termination "
        "and move-out inspection."
    )

    st.info(
        "Approving a settlement calculates the refundable "
        "amount but does NOT send money. Record a refund "
        "only after payment has been completed outside "
        "Blue Moon Apartments."
    )

    # ------------------------------------------------------
    # DISPLAY SUCCESS MESSAGE
    # ------------------------------------------------------

    message = st.session_state.pop(
        "bm_deposit_message",
        None,
    )

    if message:
        st.success(message)

    # ------------------------------------------------------
    # LOAD SETTLEMENT DATA
    # ------------------------------------------------------

    try:
        eligible = get_eligible_deposit_leases(
            admin_id
        )

        settlements = get_deposit_settlements(
            admin_id,
            limit=500,
        )

    except PermissionError as exc:
        st.error(str(exc))
        return

    except Exception:
        logger.exception(
            "Unable to load deposit settlement records"
        )

        st.error(
            "Unable to load deposit settlements. "
            "Check database setup and application logs."
        )
        return

    # ======================================================
    # SECTION 1 — CREATE NEW SETTLEMENT
    # ======================================================

    with st.expander(
        "Create New Settlement",
        expanded=not bool(settlements),
    ):

        if not eligible:

            st.caption(
                "No terminated leases are currently "
                "eligible for a new settlement draft."
            )

        else:

            available = {
                row["lease_id"]: row
                for row in eligible
            }

            with st.form(
                "bm_deposit_create_form"
            ):

                lease_id = st.selectbox(
                    "Terminated lease *",
                    options=list(available),
                    format_func=lambda value: (
                        f"{available[value]['resident']} "
                        f"· Unit {available[value]['unit']} "
                        f"· Deposit "
                        f"{_usd(available[value]['deposit'])} "
                        f"· Inspection "
                        f"{'Approved' if available[value]['inspection_approved'] else 'Pending'}"
                    ),
                )

                notes = st.text_area(
                    "Settlement notes *",
                    placeholder=(
                        "Describe why this security deposit "
                        "settlement is being prepared."
                    ),
                    max_chars=2000,
                    height=120,
                )

                create_submitted = (
                    st.form_submit_button(
                        "Create Draft Settlement",
                        type="primary",
                        disabled=not can_edit,
                    )
                )

            if create_submitted:

                _perform(
                    lambda: create_deposit_settlement(
                        admin_id,
                        lease_id,
                        notes=notes,
                    ),
                    "Draft settlement created successfully.",
                    select_created=True,
                )

    st.divider()

    # ======================================================
    # SECTION 2 — SELECT EXISTING SETTLEMENT
    # ======================================================

    st.markdown(
        "#### Review a Settlement"
    )

    if not settlements:

        st.info(
            "No deposit settlements have been created yet."
        )

        return

    by_id = {
        item["id"]: item
        for item in settlements
    }

    settlement_ids = list(
        by_id
    )

    if (
        st.session_state.get(
            "bm_deposit_selected_id"
        )
        not in by_id
    ):
        st.session_state[
            "bm_deposit_selected_id"
        ] = settlement_ids[0]

    settlement_id = st.selectbox(
        "Select settlement",
        options=settlement_ids,
        format_func=lambda value: (
            f"#{value} "
            f"· {by_id[value]['resident']} "
            f"· Unit {by_id[value]['unit']} "
            f"· {by_id[value]['status'].replace('_', ' ').title()}"
        ),
        key="bm_deposit_selected_id",
    )

    selected = by_id[
        settlement_id
    ]

    status = selected[
        "status"
    ]

    refund = Decimal(
        str(selected["refund"])
    )

    # ======================================================
    # SECTION 3 — RESIDENT AND LEASE INFORMATION
    # ======================================================

    st.markdown(
        "#### Resident & Lease Information"
    )

    with st.container(
        border=True
    ):

        st.write(
            f"**Resident:** {selected['resident']}"
        )

        st.write(
            f"**Apartment:** Unit {selected['unit']}"
        )

        st.write(
            f"**Lease ID:** {selected['lease_id']}"
        )

        st.write(
            "**Settlement Status:** "
            f"{status.replace('_', ' ').title()}"
        )

        st.write(
            f"**Settlement Notes:** {selected['notes']}"
        )

    # ======================================================
    # SECTION 4 — FINANCIAL SUMMARY
    # ======================================================

    st.markdown(
        "#### Security Deposit Financial Summary"
    )

    col1, col2, col3 = st.columns(
        3
    )

    with col1:
        st.metric(
            "Original Deposit",
            _usd(
                selected["deposit"]
            ),
        )

    with col2:
        st.metric(
            "Total Deductions",
            _usd(
                selected["deductions_total"]
            ),
        )

    with col3:

        label = (
            "Estimated Refund"
            if status == "draft"
            else "Approved Refund"
        )

        st.metric(
            label,
            _usd(refund),
        )

    # ------------------------------------------------------
    # SETTLEMENT STATUS MESSAGES
    # ------------------------------------------------------

    if status == "draft":

        st.info(
            f"Estimated refundable amount: "
            f"{_usd(refund)}"
        )

        st.caption(
            "This amount may change while deductions "
            "are being added or removed. It becomes "
            "final only after settlement approval."
        )

    elif status == "approved":

        st.success(
            f"Approved refundable balance: "
            f"{_usd(refund)}"
        )

        st.caption(
            "The amount above has been approved, "
            "but no external refund has been "
            "recorded yet."
        )

    elif status == "refunded":

        st.success(
            f"External refund recorded: "
            f"{_usd(refund)}"
        )

        st.write(
            "**Refund Method:** "
            f"{selected['refund_method'] or '—'}"
        )

        st.write(
            "**Payment Reference:** "
            f"{selected['refund_reference'] or '—'}"
        )

        st.write(
            "**Refund Date:** "
            f"{selected['refunded_on'] or '—'}"
        )

    elif status == "closed_no_refund":

        st.info(
            "Settlement completed with no "
            "refundable balance."
        )

    st.divider()

    # ======================================================
    # SECTION 5 — ITEMIZED DEDUCTIONS
    # ======================================================

    st.markdown(
        "#### Itemized Deductions"
    )

    deductions = selected[
        "deductions"
    ]

    if deductions:

        st.dataframe(
            [
                {
                    "ID": row["id"],
                    "Category": row["category"],
                    "Description": row["description"],
                    "Amount": _usd(
                        row["amount"]
                    ),
                }
                for row in deductions
            ],
            hide_index=True,
            use_container_width=True,
        )

    else:

        st.caption(
            "No deductions have been recorded. "
            "The full security deposit is refundable "
            "if the settlement is approved."
        )

    # ======================================================
    # SECTION 6 — DRAFT SETTLEMENT OPERATIONS
    # ======================================================

    if status == "draft":

        # --------------------------------------------------
        # ADD ITEMIZED DEDUCTION
        # --------------------------------------------------

        st.markdown(
            "#### Add a Deduction"
        )

        with st.form(
            f"bm_deposit_deduction_add_{settlement_id}"
        ):

            category = st.selectbox(
                "Deduction Category *",
                options=DEDUCTION_CATEGORIES,
            )

            description = st.text_area(
                "Reason and Supporting Details *",
                placeholder=(
                    "Describe the charge and why "
                    "the deduction is applicable."
                ),
                max_chars=2000,
                height=120,
            )

            amount = st.number_input(
                "Deduction Amount ($) *",
                min_value=0.01,
                max_value=99999999.99,
                value=25.00,
                step=0.01,
                format="%.2f",
            )

            add_submitted = (
                st.form_submit_button(
                    "Add Deduction",
                    disabled=not can_edit,
                )
            )

        if add_submitted:

            _perform(
                lambda: add_deposit_deduction(
                    admin_id,
                    settlement_id,
                    category=category,
                    description=description,
                    amount=f"{amount:.2f}",
                ),
                "Itemized deduction added successfully.",
            )

        # --------------------------------------------------
        # REMOVE DRAFT DEDUCTION
        # --------------------------------------------------

        if deductions:

            with st.expander(
                "Remove Draft Deduction"
            ):

                deduction_by_id = {
                    row["id"]: row
                    for row in deductions
                }

                with st.form(
                    f"bm_deposit_deduction_remove_{settlement_id}"
                ):

                    deduction_id = st.selectbox(
                        "Select Deduction to Remove",
                        options=list(
                            deduction_by_id
                        ),
                        format_func=lambda value: (
                            f"#{value} "
                            f"· {deduction_by_id[value]['category']} "
                            f"· {_usd(deduction_by_id[value]['amount'])}"
                        ),
                    )

                    confirm_remove = st.checkbox(
                        "Confirm removal of this deduction"
                    )

                    remove_submitted = (
                        st.form_submit_button(
                            "Remove Deduction",
                            disabled=not can_edit,
                        )
                    )

                if remove_submitted:

                    if not confirm_remove:

                        st.error(
                            "Please confirm deduction "
                            "removal first."
                        )

                    else:

                        _perform(
                            lambda: remove_deposit_deduction(
                                admin_id,
                                settlement_id,
                                deduction_id,
                            ),
                            "Draft deduction removed successfully.",
                        )

        # --------------------------------------------------
        # APPROVE DEPOSIT SETTLEMENT
        # --------------------------------------------------

        st.divider()

        st.markdown(
            "#### Approve Settlement"
        )

        st.warning(
            "Approval locks the deduction amounts. "
            "The associated move-out inspection must "
            "already be approved. This action does "
            "not send a refund."
        )

        with st.form(
            f"bm_deposit_approve_{settlement_id}"
        ):

            confirm_approval = st.checkbox(
                "I have reviewed the documented "
                "deductions and refundable balance."
            )

            approval_submitted = (
                st.form_submit_button(
                    "Approve Settlement",
                    type="primary",
                    disabled=not can_approve,
                )
            )

        if approval_submitted:

            if not confirm_approval:

                st.error(
                    "Please confirm the settlement "
                    "review before approval."
                )

            else:

                _perform(
                    lambda: approve_deposit_settlement(
                        admin_id,
                        settlement_id,
                    ),
                    "Settlement approved successfully. "
                    "The refundable amount is now final.",
                )

    # ======================================================
    # SECTION 7 — APPROVED SETTLEMENT OPERATIONS
    # ======================================================

    elif status == "approved":

        if refund > 0:

            # ----------------------------------------------
            # RECORD COMPLETED EXTERNAL REFUND
            # ----------------------------------------------

            st.markdown(
                "#### Record an External Refund"
            )

            st.warning(
                "Only complete this form AFTER the "
                "refund has been paid externally. "
                "This form does not transfer money."
            )

            with st.form(
                f"bm_deposit_refund_{settlement_id}"
            ):

                paid_amount = st.number_input(
                    "Amount Actually Paid ($) *",
                    min_value=0.01,
                    max_value=99999999.99,
                    value=float(refund),
                    step=0.01,
                    format="%.2f",
                )

                refund_method = st.selectbox(
                    "Refund Method *",
                    options=REFUND_METHODS,
                )

                refund_reference = st.text_input(
                    "External Transaction or Check Reference *",
                    max_chars=120,
                    placeholder=(
                        "Enter bank transaction ID "
                        "or check number."
                    ),
                )

                refunded_on = st.date_input(
                    "Actual Refund Date *",
                    value=date.today(),
                    max_value=date.today(),
                )

                confirmed_payment = st.checkbox(
                    "I confirm that this refund has "
                    "already been sent externally."
                )

                refund_submitted = (
                    st.form_submit_button(
                        "Record Completed Refund",
                        type="primary",
                        disabled=not can_refund,
                    )
                )

            if refund_submitted:

                if not confirmed_payment:

                    st.error(
                        "Please confirm that the "
                        "external payment has been completed."
                    )

                else:

                    _perform(
                        lambda: record_external_refund(
                            admin_id,
                            settlement_id,
                            confirmed_amount=f"{paid_amount:.2f}",
                            refund_method=refund_method,
                            refund_reference=refund_reference,
                            refunded_on=refunded_on,
                        ),
                        "External refund recorded successfully "
                        "and settlement closed.",
                    )

        else:

            # ----------------------------------------------
            # CLOSE ZERO-REFUND SETTLEMENT
            # ----------------------------------------------

            st.markdown(
                "#### Close Zero-Refund Settlement"
            )

            st.info(
                "All of the recorded security deposit "
                "has been allocated to approved deductions. "
                "No refund is due."
            )

            with st.form(
                f"bm_deposit_close_zero_{settlement_id}"
            ):

                confirm_zero = st.checkbox(
                    "I confirm no refund is due and "
                    "all approved deductions are final."
                )

                close_submitted = (
                    st.form_submit_button(
                        "Close Settlement",
                        type="primary",
                        disabled=not can_approve,
                    )
                )

            if close_submitted:

                if not confirm_zero:

                    st.error(
                        "Please confirm the zero-refund "
                        "settlement first."
                    )

                else:

                    _perform(
                        lambda: close_zero_refund_settlement(
                            admin_id,
                            settlement_id,
                        ),
                        "Zero-refund settlement closed successfully.",
                    )

    # ======================================================
    # SECTION 8 — SETTLEMENT AUDIT HISTORY
    # ======================================================

    st.divider()

    st.markdown(
        "#### Settlement Audit History"
    )

    if selected["events"]:

        st.dataframe(
            [
                {
                    "When": row["created_at"],
                    "Action": (
                        row["action"]
                        .replace("_", " ")
                        .title()
                    ),
                    "Details": row["details"],
                    "Admin ID": row["admin_id"],
                }
                for row in selected["events"]
            ],
            hide_index=True,
            use_container_width=True,
        )

    else:

        st.caption(
            "No audit events have been recorded yet."
        )

    # ======================================================
    # SECTION 9 — ALL DEPOSIT SETTLEMENTS
    # ======================================================

    with st.expander(
        "All Deposit Settlements"
    ):

        st.dataframe(
            [
                {
                    "ID": item["id"],
                    "Resident": item["resident"],
                    "Unit": item["unit"],
                    "Status": (
                        item["status"]
                        .replace("_", " ")
                        .title()
                    ),
                    "Deposit": _usd(
                        item["deposit"]
                    ),
                    "Deductions": _usd(
                        item["deductions_total"]
                    ),
                    "Refundable": _usd(
                        item["refund"]
                    ),
                }
                for item in settlements
            ],
            hide_index=True,
            use_container_width=True,
        )
