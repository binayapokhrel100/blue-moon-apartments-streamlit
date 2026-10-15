
"""Blue Moon Apartments — Security Deposit Settlement Service.

This module records deposit accounting decisions.
It does NOT send refunds or collect payments.

Supported workflow:
    draft -> approved -> refunded
    draft -> approved -> closed_no_refund
"""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select, update

from database.db import get_db_session
from database.models import (
    Apartment,
    DepositDeduction,
    DepositSettlement,
    DepositSettlementEvent,
    Lease,
    MoveOutInspection,
    User,
    utc_now,
)

from services.admin_management_service import _require_admin


DEDUCTION_CATEGORIES = (
    "Cleaning",
    "Repairs",
    "Unpaid Rent",
    "Other",
)

REFUND_METHODS = (
    "Bank Transfer",
    "Check",
    "Original Payment Method",
    "Other",
)

MONEY_LIMIT = Decimal("99999999.99")
CENT = Decimal("0.01")


# ==========================================================
# VALIDATION
# ==========================================================

def _money(value, *, allow_zero=True) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(
            "Enter a valid dollar amount."
        ) from None

    if not amount.is_finite():
        raise ValueError(
            "Dollar amounts must be finite."
        )

    if amount < 0 or amount > MONEY_LIMIT:
        raise ValueError(
            "Amount must be between $0 and $99,999,999.99."
        )

    if not allow_zero and amount == 0:
        raise ValueError(
            "Deduction amount must be greater than zero."
        )

    if amount != amount.quantize(CENT):
        raise ValueError(
            "Dollar amounts cannot have more "
            "than two decimal places."
        )

    return amount.quantize(CENT)


def _notes(value: str, label: str) -> str:
    cleaned = (value or "").strip()

    if not 10 <= len(cleaned) <= 2000:
        raise ValueError(
            f"{label} must contain 10–2,000 characters."
        )

    return cleaned


def _settlement(db, settlement_id: int):
    item = db.get(DepositSettlement, settlement_id)

    if item is None:
        raise ValueError(
            "Deposit settlement not found."
        )

    return item


def _draft(db, settlement_id: int):
    item = _settlement(db, settlement_id)

    if item.status != "draft":
        raise ValueError(
            "Only draft settlements can be edited."
        )

    return item


def _deduction_total(db, settlement_id: int) -> Decimal:
    value = db.scalar(
        select(func.sum(DepositDeduction.amount)).where(
            DepositDeduction.settlement_id == settlement_id
        )
    )

    return Decimal(str(value or 0)).quantize(CENT)


def _audit(
    db,
    settlement_id: int,
    admin_id: int,
    action: str,
    details: str,
) -> None:
    db.add(
        DepositSettlementEvent(
            settlement_id=settlement_id,
            admin_user_id=admin_id,
            action=action,
            details=details,
        )
    )


# ==========================================================
# ELIGIBLE TERMINATED LEASES
# ==========================================================

def get_eligible_deposit_leases(admin_id: int) -> list[dict]:
    """Return terminated leases without existing settlements."""

    with get_db_session() as db:
        _require_admin(db, admin_id, permission="deposits.read")

        settled_lease_ids = set(
            db.scalars(
                select(DepositSettlement.lease_id)
            ).all()
        )

        rows = db.execute(
            select(Lease, User, Apartment)
            .join(User, Lease.resident_id == User.id)
            .join(
                Apartment,
                Lease.apartment_id == Apartment.id,
            )
            .where(
                func.lower(Lease.status) == "terminated",
                func.lower(User.role) == "resident",
            )
            .order_by(Lease.id.desc())
            .limit(300)
        ).all()

        result = []

        for lease, resident, apartment in rows:
            if lease.id in settled_lease_ids:
                continue

            inspection_approved = db.scalar(
                select(MoveOutInspection.id).where(
                    MoveOutInspection.lease_id == lease.id,
                    MoveOutInspection.status == "approved",
                ).limit(1)
            ) is not None

            result.append(
                {
                    "lease_id": lease.id,
                    "resident_id": resident.id,
                    "resident": resident.full_name,
                    "email": resident.email,
                    "unit": apartment.unit_number,
                    "deposit": str(
                        _money(lease.security_deposit or 0)
                    ),
                    "inspection_approved": inspection_approved,
                }
            )

        return result


# ==========================================================
# CREATE DRAFT SETTLEMENT
# ==========================================================

def create_deposit_settlement(
    admin_id: int,
    lease_id: int,
    *,
    notes: str,
) -> int:
    """Create a draft; no money moves and no deductions are applied."""

    cleaned_notes = _notes(
        notes,
        "Settlement notes",
    )

    with get_db_session() as db:
        _require_admin(db, admin_id, permission="deposits.edit")

        lease = db.get(Lease, lease_id)

        if lease is None:
            raise ValueError("Lease not found.")

        if str(lease.status or "").lower() != "terminated":
            raise ValueError(
                "Only terminated leases can receive "
                "a deposit settlement. Transferred "
                "leases carry their deposit forward."
            )

        existing = db.scalar(
            select(DepositSettlement.id).where(
                DepositSettlement.lease_id == lease_id
            )
        )

        if existing is not None:
            raise ValueError(
                "This lease already has a deposit settlement."
            )

        deposit = _money(
            lease.security_deposit or 0
        )

        item = DepositSettlement(
            lease_id=lease.id,
            resident_id=lease.resident_id,
            apartment_id=lease.apartment_id,
            deposit_amount=deposit,
            approved_deductions=Decimal("0.00"),
            approved_refund=Decimal("0.00"),
            status="draft",
            notes=cleaned_notes,
            created_by=admin_id,
        )

        db.add(item)
        db.flush()

        _audit(
            db,
            item.id,
            admin_id,
            "created",
            (
                f"Draft created for lease {lease.id}; "
                f"recorded deposit ${deposit:.2f}."
            ),
        )

        return item.id


# ==========================================================
# ADD ITEMIZED DEDUCTION
# ==========================================================

def add_deposit_deduction(
    admin_id: int,
    settlement_id: int,
    *,
    category: str,
    description: str,
    amount,
) -> int:

    if category not in DEDUCTION_CATEGORIES:
        raise ValueError(
            "Choose a valid deduction category."
        )

    cleaned = _notes(
        description,
        "Deduction description",
    )

    deduction_amount = _money(
        amount,
        allow_zero=False,
    )

    with get_db_session() as db:
        _require_admin(db, admin_id, permission="deposits.edit")

        item = _draft(
            db,
            settlement_id,
        )

        current_total = _deduction_total(
            db,
            settlement_id,
        )

        if current_total + deduction_amount > item.deposit_amount:
            raise ValueError(
                "Total deductions cannot exceed the "
                "recorded security deposit. Additional "
                "claims must be handled separately."
            )

        deduction = DepositDeduction(
            settlement_id=item.id,
            category=category,
            description=cleaned,
            amount=deduction_amount,
            created_by=admin_id,
        )

        db.add(deduction)
        db.flush()

        _audit(
            db,
            item.id,
            admin_id,
            "deduction_added",
            (
                f"{category}: ${deduction_amount:.2f}; "
                f"{cleaned}"
            ),
        )

        return deduction.id


# ==========================================================
# REMOVE DRAFT DEDUCTION
# ==========================================================

def remove_deposit_deduction(
    admin_id: int,
    settlement_id: int,
    deduction_id: int,
) -> None:

    with get_db_session() as db:
        _require_admin(db, admin_id, permission="deposits.edit")

        _draft(
            db,
            settlement_id,
        )

        deduction = db.get(
            DepositDeduction,
            deduction_id,
        )

        if (
            deduction is None
            or deduction.settlement_id != settlement_id
        ):
            raise ValueError(
                "Deduction not found for this settlement."
            )

        description = (
            f"{deduction.category}: "
            f"${deduction.amount:.2f}; "
            f"{deduction.description}"
        )

        db.delete(deduction)

        _audit(
            db,
            settlement_id,
            admin_id,
            "deduction_removed",
            description,
        )


# ==========================================================
# APPROVE DEPOSIT SETTLEMENT
# ==========================================================

def approve_deposit_settlement(
    admin_id: int,
    settlement_id: int,
) -> None:
    """Freeze deductions and calculate the approved refund."""

    with get_db_session() as db:
        _require_admin(db, admin_id, permission="deposits.approve")

        item = _draft(
            db,
            settlement_id,
        )

        inspection = db.scalar(
            select(MoveOutInspection.id).where(
                MoveOutInspection.lease_id == item.lease_id,
                MoveOutInspection.resident_id == item.resident_id,
                MoveOutInspection.apartment_id == item.apartment_id,
                MoveOutInspection.status == "approved",
            ).limit(1)
        )

        if inspection is None:
            raise ValueError(
                "The associated move-out inspection "
                "must be approved before the deposit "
                "settlement can be approved."
            )

        total = _deduction_total(
            db,
            item.id,
        )

        if total > item.deposit_amount:
            raise ValueError(
                "Deductions exceed the security deposit."
            )

        refund = (
            item.deposit_amount - total
        ).quantize(CENT)

        result = db.execute(
            update(DepositSettlement)
            .where(
                DepositSettlement.id == settlement_id,
                DepositSettlement.status == "draft",
            )
            .values(
                approved_deductions=total,
                approved_refund=refund,
                status="approved",
                approved_by=admin_id,
                approved_at=utc_now(),
            )
        )

        if result.rowcount != 1:
            raise ValueError(
                "Settlement changed during approval. "
                "Refresh and retry."
            )

        _audit(
            db,
            settlement_id,
            admin_id,
            "approved",
            (
                f"Deposit ${item.deposit_amount:.2f}; "
                f"deductions ${total:.2f}; "
                f"approved refund ${refund:.2f}. "
                "No payment was sent."
            ),
        )


# ==========================================================
# RECORD AN EXTERNALLY COMPLETED REFUND
# ==========================================================

def record_external_refund(
    admin_id: int,
    settlement_id: int,
    *,
    confirmed_amount,
    refund_method: str,
    refund_reference: str,
    refunded_on: date,
) -> None:
    """
    Record an already completed external payment.

    This function DOES NOT send money.
    """

    amount = _money(
        confirmed_amount,
        allow_zero=False,
    )

    if refund_method not in REFUND_METHODS:
        raise ValueError(
            "Choose a valid refund method."
        )

    reference = (refund_reference or "").strip()

    if not 6 <= len(reference) <= 120:
        raise ValueError(
            "External refund reference must contain "
            "6–120 characters."
        )

    if (
        not isinstance(refunded_on, date)
        or isinstance(refunded_on, datetime)
        or refunded_on > date.today()
    ):
        raise ValueError(
            "Refund date must be a valid date "
            "that is not in the future."
        )

    with get_db_session() as db:
        _require_admin(db, admin_id, permission="refunds.record")

        item = _settlement(
            db,
            settlement_id,
        )

        if item.status != "approved":
            raise ValueError(
                "Only an approved settlement can "
                "have a refund recorded."
            )

        if amount != item.approved_refund:
            raise ValueError(
                "Confirmed external payment amount "
                "must match the approved refund exactly."
            )

        result = db.execute(
            update(DepositSettlement)
            .where(
                DepositSettlement.id == settlement_id,
                DepositSettlement.status == "approved",
            )
            .values(
                status="refunded",
                refund_method=refund_method,
                refund_reference=reference,
                refunded_on=refunded_on,
                refund_recorded_by=admin_id,
                closed_at=utc_now(),
            )
        )

        if result.rowcount != 1:
            raise ValueError(
                "Settlement changed while recording "
                "the refund."
            )

        _audit(
            db,
            settlement_id,
            admin_id,
            "refund_recorded",
            (
                f"External {refund_method} refund of "
                f"${amount:.2f}, dated {refunded_on}, "
                f"reference {reference}."
            ),
        )


# ==========================================================
# CLOSE APPROVED SETTLEMENT WITH ZERO REFUND
# ==========================================================

def close_zero_refund_settlement(
    admin_id: int,
    settlement_id: int,
) -> None:

    with get_db_session() as db:
        _require_admin(db, admin_id, permission="deposits.approve")

        item = _settlement(
            db,
            settlement_id,
        )

        if item.status != "approved":
            raise ValueError(
                "Settlement must be approved first."
            )

        if item.approved_refund != Decimal("0.00"):
            raise ValueError(
                "This settlement has a refundable balance. "
                "Record the completed external refund instead."
            )

        result = db.execute(
            update(DepositSettlement)
            .where(
                DepositSettlement.id == settlement_id,
                DepositSettlement.status == "approved",
            )
            .values(
                status="closed_no_refund",
                closed_at=utc_now(),
            )
        )

        if result.rowcount != 1:
            raise ValueError(
                "Settlement changed while closing it."
            )

        _audit(
            db,
            settlement_id,
            admin_id,
            "closed_no_refund",
            "Approved settlement closed with a $0.00 refund.",
        )


# ==========================================================
# READ SETTLEMENTS AND ITEMIZED HISTORY
# ==========================================================

def get_deposit_settlements(
    admin_id: int,
    limit: int = 200,
) -> list[dict]:
    """Return settlement summaries for the admin interface."""

    with get_db_session() as db:
        _require_admin(db, admin_id, permission="deposits.read")

        items = db.scalars(
            select(DepositSettlement)
            .order_by(DepositSettlement.id.desc())
            .limit(max(1, min(int(limit), 500)))
        ).all()

        results = []

        for item in items:

            resident = db.get(
                User,
                item.resident_id,
            )

            apartment = db.get(
                Apartment,
                item.apartment_id,
            )

            deductions = db.scalars(
                select(DepositDeduction)
                .where(
                    DepositDeduction.settlement_id == item.id
                )
                .order_by(DepositDeduction.id)
            ).all()

            events = db.scalars(
                select(DepositSettlementEvent)
                .where(
                    DepositSettlementEvent.settlement_id == item.id
                )
                .order_by(DepositSettlementEvent.id)
            ).all()

            total = sum(
                (
                    deduction.amount
                    for deduction in deductions
                ),
                Decimal("0.00"),
            )

            refundable = (
                item.deposit_amount - total
                if item.status == "draft"
                else item.approved_refund
            )

            results.append(
                {
                    "id": item.id,
                    "lease_id": item.lease_id,
                    "resident": (
                        resident.full_name
                        if resident
                        else f"Resident #{item.resident_id}"
                    ),
                    "unit": (
                        apartment.unit_number
                        if apartment
                        else "Unknown"
                    ),
                    "deposit": item.deposit_amount,
                    "deductions_total": (
                        total if item.status == "draft"
                        else item.approved_deductions
                    ),
                    "refund": refundable,
                    "status": item.status,
                    "notes": item.notes,
                    "refund_method": item.refund_method,
                    "refund_reference": item.refund_reference,
                    "refunded_on": item.refunded_on,
                    "created_at": item.created_at,
                    "deductions": [
                        {
                            "id": d.id,
                            "category": d.category,
                            "description": d.description,
                            "amount": d.amount,
                        }
                        for d in deductions
                    ],
                    "events": [
                        {
                            "action": e.action,
                            "details": e.details,
                            "admin_id": e.admin_user_id,
                            "created_at": e.created_at,
                        }
                        for e in events
                    ],
                }
            )

        return results
