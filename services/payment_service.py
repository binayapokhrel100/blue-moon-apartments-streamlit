from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from secrets import randbelow

from sqlalchemy import func, select

from database.db import get_db_session
from database.models import (
    Lease,
    Notification,
    Payment,
)


MONEY = Decimal("0.01")


def _to_money(
    value: Decimal | str | float | int,
) -> Decimal:

    return Decimal(
        str(value)
    ).quantize(
        MONEY,
        rounding=ROUND_HALF_UP,
    )


def generate_confirmation_number() -> str:

    today = datetime.now()

    random_part = randbelow(9000) + 1000

    return (
        f"BMP-"
        f"{today:%Y%m%d}-"
        f"{random_part}"
    )


def validate_payment_amount(
    amount: Decimal,
    balance: Decimal,
) -> None:

    amount = _to_money(amount)
    balance = _to_money(balance)

    if amount <= Decimal("0.00"):
        raise ValueError(
            "Payment amount must be greater than zero."
        )

    if amount > balance:
        raise ValueError(
            "Payment amount cannot exceed the current balance."
        )


def get_active_lease(
    user_id: int,
) -> dict | None:

    with get_db_session() as db:

        statement = (
            select(Lease)
            .where(
                Lease.resident_id == user_id,
                Lease.status == "active",
            )
            .order_by(
                Lease.end_date.desc()
            )
        )

        lease = db.scalar(statement)

        if lease is None:
            return None

        return {
            "id": lease.id,
            "resident_id": lease.resident_id,
            "apartment_id": lease.apartment_id,
            "start_date": lease.start_date,
            "end_date": lease.end_date,
            "monthly_rent": _to_money(
                lease.monthly_rent
            ),
            "status": lease.status,
        }


def get_payment_summary(
    user_id: int,
    payment_month: date | None = None,
) -> dict:

    lease = get_active_lease(user_id)

    if lease is None:
        return {
            "monthly_rent": Decimal("0.00"),
            "amount_paid": Decimal("0.00"),
            "balance": Decimal("0.00"),
            "due_date": None,
            "status": "No Active Lease",
        }

    today = date.today()

    if payment_month is None:
        payment_month = date(
            today.year,
            today.month,
            1,
        )

    normalized_month = date(
        payment_month.year,
        payment_month.month,
        1,
    )

    monthly_rent = _to_money(
        lease["monthly_rent"]
    )

    with get_db_session() as db:

        statement = (
            select(
                func.coalesce(
                    func.sum(Payment.amount),
                    0,
                )
            )
            .where(
                Payment.resident_id == user_id,
                Payment.payment_month
                == normalized_month,
                Payment.status == "confirmed",
            )
        )

        total_paid_raw = db.scalar(
            statement
        )

    amount_paid = _to_money(
        total_paid_raw or 0
    )

    balance = max(
        Decimal("0.00"),
        monthly_rent - amount_paid,
    )

    due_date = normalized_month

    if balance == Decimal("0.00"):
        status = "Paid"

    elif amount_paid > Decimal("0.00"):
        status = "Partially Paid"

    elif today > due_date:
        status = "Overdue"

    else:
        status = "Due"

    return {
        "monthly_rent": monthly_rent,
        "amount_paid": amount_paid,
        "balance": balance,
        "due_date": due_date,
        "status": status,
    }


def get_payment_history(
    user_id: int,
) -> list[dict]:

    with get_db_session() as db:

        statement = (
            select(Payment)
            .where(
                Payment.resident_id == user_id
            )
            .order_by(
                Payment.paid_at.desc()
            )
        )

        payments = db.scalars(
            statement
        ).all()

        return [
            {
                "id": payment.id,
                "amount": _to_money(
                    payment.amount
                ),
                "payment_month": (
                    payment.payment_month
                ),
                "payment_method": (
                    payment.payment_method
                ),
                "status": payment.status,
                "confirmation_number": (
                    payment.confirmation_number
                ),
                "paid_at": payment.paid_at,
            }
            for payment in payments
        ]


def create_payment(
    user_id: int,
    amount: Decimal,
    payment_method: str,
    payment_month: date | None = None,
) -> dict:

    today = date.today()

    if payment_month is None:
        payment_month = date(
            today.year,
            today.month,
            1,
        )

    payment_month = date(
        payment_month.year,
        payment_month.month,
        1,
    )

    summary = get_payment_summary(
        user_id=user_id,
        payment_month=payment_month,
    )

    balance = summary["balance"]

    amount = _to_money(amount)

    validate_payment_amount(
        amount=amount,
        balance=balance,
    )

    lease = get_active_lease(
        user_id
    )

    if lease is None:
        raise ValueError(
            "No active lease was found."
        )

    confirmation = (
        generate_confirmation_number()
    )

    with get_db_session() as db:

        payment = Payment(
            resident_id=user_id,
            lease_id=lease["id"],
            amount=amount,
            payment_month=payment_month,
            payment_method=payment_method,
            status="confirmed",
            confirmation_number=confirmation,
        )

        db.add(payment)
        db.flush()

        notification = Notification(
            user_id=user_id,
            title="Payment Confirmed",
            message=(
                f"Your rent payment of "
                f"${amount:,.2f} was received. "
                f"Confirmation: {confirmation}"
            ),
            notification_type="payment",
            is_read=False,
            is_alert=False,
        )

        db.add(notification)

        return {
            "id": payment.id,
            "amount": amount,
            "payment_month": payment_month,
            "payment_method": payment_method,
            "status": payment.status,
            "confirmation_number": (
                payment.confirmation_number
            ),
            "paid_at": payment.paid_at,
        }