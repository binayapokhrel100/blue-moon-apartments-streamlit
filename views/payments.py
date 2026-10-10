
"""Resident rent payments page."""

import html
from decimal import Decimal, InvalidOperation

import pandas as pd
import streamlit as st

from components.cards import metric_card
from components.header import render_header
from components.html_renderer import render_html
from core.session import get_current_user
from services.payment_service import (
    create_payment,
    get_payment_history,
    get_payment_summary,
)


def money(value) -> str:
    """Format a monetary value."""
    return f"${Decimal(str(value)):,.2f}"


def render_payments() -> None:
    """Render the resident payments page."""

    user = get_current_user() or {}
    user_id = user.get("id")

    if user_id is None:
        st.error("Unable to identify the current resident.")
        return

    # ---------------------------------------------
    # PAYMENT SUCCESS MESSAGE
    # ---------------------------------------------

    if "payment_success" in st.session_state:
        st.success(st.session_state.pop("payment_success"))

    summary = get_payment_summary(user_id)

    monthly_rent = Decimal(str(summary["monthly_rent"]))
    amount_paid = Decimal(str(summary["amount_paid"]))
    balance = Decimal(str(summary["balance"]))
    status = str(summary["status"])
    due_date = summary.get("due_date")

    render_header("Payments")

    # ---------------------------------------------
    # PAGE TITLE
    # ---------------------------------------------

    render_html("""
    <h1 class="page-title">Payments</h1>
    <p class="page-description">
        View your rent balance, payment status and payment history.
    </p>
    """)

    # ---------------------------------------------
    # METRIC CARDS
    # ---------------------------------------------

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        metric_card(
            "Monthly Rent",
            money(monthly_rent),
            "Current lease",
        )

    with col2:
        metric_card(
            "Amount Paid",
            money(amount_paid),
            "This month",
        )

    with col3:
        metric_card(
            "Current Balance",
            money(balance),
            status,
        )

    with col4:
        due_text = (
            due_date.strftime("%b %d, %Y")
            if due_date
            else "N/A"
        )

        metric_card(
            "Due Date",
            due_text,
            status,
        )

    st.write("")

    left, right = st.columns([1.1, 1], gap="large")

    # =============================================
    # MAKE PAYMENT
    # =============================================

    with left:
        render_html("""
        <div class="section-heading">
            <h3>Make a Payment</h3>
            <p>
                Payments in this portfolio application
                are simulated.
            </p>
        </div>
        """)

        if balance <= Decimal("0.00"):
            st.success(
                "Your rent balance for this month is fully paid."
            )

        else:
            with st.form("rent_payment_form"):

                amount = st.number_input(
                    "Payment amount",
                    min_value=1.00,
                    max_value=float(balance),
                    value=float(balance),
                    step=25.00,
                    format="%.2f",
                )

                payment_method = st.selectbox(
                    "Payment method",
                    [
                        "Bank Account •••• 4821",
                        "Demo Card •••• 9012",
                    ],
                )

                st.caption(
                    "No real bank or card information is processed."
                )

                submitted = st.form_submit_button(
                    "Review & Confirm Payment",
                    use_container_width=True,
                    type="primary",
                )

            if submitted:
                try:
                    payment_amount = Decimal(
                        str(amount)
                    ).quantize(Decimal("0.01"))

                    if payment_amount <= Decimal("0.00"):
                        raise ValueError(
                            "Payment must be greater than zero."
                        )

                    if payment_amount > balance:
                        raise ValueError(
                            "Payment cannot exceed your balance."
                        )

                    payment = create_payment(
                        user_id=user_id,
                        amount=payment_amount,
                        payment_method=payment_method,
                    )

                    st.session_state["payment_success"] = (
                        "Payment confirmed. Confirmation: "
                        f"{payment['confirmation_number']}"
                    )

                    st.rerun()

                except (ValueError, InvalidOperation) as error:
                    st.error(str(error))

    # =============================================
    # PAYMENT SUMMARY
    # =============================================

    with right:

        safe_status = html.escape(status)

        render_html(f"""
        <div class="payment-summary-card">
            <h3>Payment Summary</h3>

            <div class="summary-row">
                <span>Monthly rent</span>
                <strong>{money(monthly_rent)}</strong>
            </div>

            <div class="summary-row">
                <span>Paid</span>
                <strong>{money(amount_paid)}</strong>
            </div>

            <div class="summary-row">
                <span>Remaining</span>
                <strong>{money(balance)}</strong>
            </div>

            <div class="summary-total">
                <span>Status</span>
                <strong>{safe_status}</strong>
            </div>
        </div>
        """)

    # =============================================
    # PAYMENT HISTORY
    # =============================================

    st.write("")

    render_html("""
    <div class="section-heading">
        <h3>Payment History</h3>
        <p>Your recent confirmed rent payments.</p>
    </div>
    """)

    history = get_payment_history(user_id)

    if not history:
        st.info("No payment history found.")
        return

    rows = []

    for payment in history:

        paid_at = payment.get("paid_at")
        payment_month = payment.get("payment_month")

        rows.append(
            {
                "Date": (
                    paid_at.strftime("%b %d, %Y")
                    if paid_at else "N/A"
                ),
                "Rent Month": (
                    payment_month.strftime("%B %Y")
                    if payment_month else "N/A"
                ),
                "Amount": money(payment["amount"]),
                "Method": payment["payment_method"],
                "Status": str(
                    payment["status"]
                ).title(),
                "Confirmation": payment[
                    "confirmation_number"
                ],
            }
        )

    dataframe = pd.DataFrame(rows)

    st.dataframe(
        dataframe,
        use_container_width=True,
        hide_index=True,
    )
