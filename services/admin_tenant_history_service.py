
"""Blue Moon Apartments — read-only, admin-only resident history."""

from datetime import date, datetime, time, timezone
from decimal import Decimal

from sqlalchemy import func, select

from database.db import get_db_session
from database.models import (
    Apartment,
    ApartmentTransfer,
    DepositDeduction,
    DepositSettlement,
    DepositSettlementEvent,
    Lease,
    LeaseRenewal,
    MaintenanceRequest,
    MaintenanceUpdate,
    MoveOutInspection,
    Payment,
    TenancyEvent,
    User,
)
from services.admin_management_service import _require_admin


CONFIRMED_PAYMENT_STATUSES = {
    "confirmed",
    "completed",
    "paid",
    "succeeded",
    "success",
}


# ==========================================================
# READ-ONLY HELPERS
# ==========================================================

def _value(obj, *names, default=None):
    """Read an existing model attribute safely."""
    for name in names:
        if hasattr(obj, name):
            value = getattr(obj, name)
            if value is not None:
                return value
    return default


def _money(value) -> Decimal:
    return Decimal(
        str(value if value is not None else "0")
    ).quantize(Decimal("0.01"))


def _text(value, default="—") -> str:
    if value is None:
        return default
    result = str(value).strip()
    return result if result else default


def _rows_for_resident(db, model, resident_id: int):
    """Return records for this resident, including archived users."""

    owner_column = next(
        (
            getattr(model, name)
            for name in (
                "resident_id",
                "user_id",
                "tenant_id",
            )
            if hasattr(model, name)
        ),
        None,
    )

    if owner_column is None:
        return []

    return list(
        db.scalars(
            select(model)
            .where(owner_column == resident_id)
            .order_by(model.id.desc())
        ).all()
    )


def _event_date(value):
    if isinstance(value, (datetime, date)):
        return value
    return None


def _sort_date(value) -> datetime:
    """Normalize dates for chronological ordering."""

    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(
                timezone.utc
            ).replace(tzinfo=None)
        return value

    if isinstance(value, date):
        return datetime.combine(
            value,
            time.min,
        )

    return datetime.min


# ==========================================================
# LIST ACTIVE AND ARCHIVED RESIDENTS
# ==========================================================

def get_history_residents(
    admin_id: int,
) -> list[dict]:
    """Return residents for the history selector."""

    with get_db_session() as db:
        # Full resident-history exports contain payment and deposit data.
        # Restrict them to Super Admin under the current RBAC policy.
        _require_admin(
            db,
            admin_id,
            permission="admins.manage",
        )

        users = db.scalars(
            select(User)
            .where(
                func.lower(User.role) == "resident"
            )
            .order_by(
                User.last_name,
                User.first_name,
                User.id,
            )
        ).all()

        return [
            {
                "id": person.id,
                "name": person.full_name,
                "email": person.email,
                "active": bool(person.is_active),
                "apartment_id": person.apartment_id,
            }
            for person in users
        ]


# ==========================================================
# GET COMPLETE RESIDENT HISTORY
# ==========================================================

def get_resident_history(
    admin_id: int,
    resident_id: int,
) -> dict:
    """
    Read all available historical records for a resident.

    Includes archived residents.

    Does not update any account, apartment, lease,
    payment, inspection, or deposit record.
    """

    with get_db_session() as db:
        # Full resident-history exports contain payment and deposit data.
        # Restrict them to Super Admin under the current RBAC policy.
        _require_admin(
            db,
            admin_id,
            permission="admins.manage",
        )

        resident = db.get(
            User,
            resident_id,
        )

        if (
            resident is None
            or str(resident.role or "").lower()
            != "resident"
        ):
            raise ValueError(
                "Resident not found."
            )

        # ==============================================
        # LOAD HISTORICAL RECORDS
        # ==============================================

        leases = _rows_for_resident(
            db, Lease, resident_id
        )

        renewals = _rows_for_resident(
            db, LeaseRenewal, resident_id
        )

        transfers = _rows_for_resident(
            db, ApartmentTransfer, resident_id
        )

        payments = _rows_for_resident(
            db, Payment, resident_id
        )

        maintenance = _rows_for_resident(
            db, MaintenanceRequest, resident_id
        )

        inspections = _rows_for_resident(
            db, MoveOutInspection, resident_id
        )

        deposits = _rows_for_resident(
            db, DepositSettlement, resident_id
        )

        tenancy_events = _rows_for_resident(
            db, TenancyEvent, resident_id
        )

        # ==============================================
        # MAINTENANCE UPDATES
        # ==============================================

        request_ids = [
            request.id
            for request in maintenance
        ]

        update_fk = next(
            (
                getattr(
                    MaintenanceUpdate,
                    name,
                )
                for name in (
                    "request_id",
                    "maintenance_request_id",
                )
                if hasattr(
                    MaintenanceUpdate,
                    name,
                )
            ),
            None,
        )

        if (
            update_fk is not None
            and request_ids
        ):
            updates = list(
                db.scalars(
                    select(MaintenanceUpdate)
                    .where(
                        update_fk.in_(request_ids)
                    )
                    .order_by(
                        MaintenanceUpdate.id.desc()
                    )
                ).all()
            )
        else:
            updates = []

        update_parent_field = (
            update_fk.key
            if update_fk is not None
            else None
        )

        # ==============================================
        # DEPOSIT DEDUCTIONS AND AUDIT HISTORY
        # ==============================================

        settlement_ids = [
            settlement.id
            for settlement in deposits
        ]

        if settlement_ids:

            deductions = list(
                db.scalars(
                    select(DepositDeduction)
                    .where(
                        DepositDeduction.settlement_id.in_(
                            settlement_ids
                        )
                    )
                    .order_by(
                        DepositDeduction.id.desc()
                    )
                ).all()
            )

            deposit_events = list(
                db.scalars(
                    select(DepositSettlementEvent)
                    .where(
                        DepositSettlementEvent.settlement_id.in_(
                            settlement_ids
                        )
                    )
                    .order_by(
                        DepositSettlementEvent.id.desc()
                    )
                ).all()
            )

        else:
            deductions = []
            deposit_events = []

        # ==============================================
        # APARTMENT UNIT LOOKUP
        # ==============================================

        unit_cache = {}

        def unit(apartment_id):

            if apartment_id is None:
                return "—"

            if apartment_id not in unit_cache:

                apartment = db.get(
                    Apartment,
                    apartment_id,
                )

                unit_cache[apartment_id] = (
                    apartment.unit_number
                    if apartment
                    else f"#{apartment_id}"
                )

            return unit_cache[apartment_id]

        lease_unit = {
            lease.id: unit(lease.apartment_id)
            for lease in leases
        }

        current_unit = unit(
            resident.apartment_id
        )

        # ==============================================
        # ACTIVITY TIMELINE HELPER
        # ==============================================

        events = []

        def add_event(
            when,
            category,
            title,
            details,
            amount=None,
        ):
            when = _event_date(when)

            if when is None:
                return

            events.append(
                {
                    "date": when,
                    "category": category,
                    "event": title,
                    "details": details,
                    "amount": (
                        _money(amount)
                        if amount is not None
                        else None
                    ),
                }
            )

        add_event(
            _value(
                resident,
                "created_at",
            ),
            "Account",
            "Resident account created",
            resident.email,
        )

        # ==============================================
        # TENANCY / ACCOUNT EVENTS
        # ==============================================

        tenancy_rows = []

        for item in tenancy_events:

            row = {
                "Date": item.effective_date,
                "Action": (
                    _text(item.event_type)
                    .replace("_", " ")
                    .title()
                ),
                "Unit": unit(
                    item.apartment_id
                ),
                "Lease ID": item.lease_id,
                "Reason": item.reason,
                "Admin ID": item.admin_user_id,
            }

            tenancy_rows.append(row)

            add_event(
                item.effective_date,
                "Tenancy",
                row["Action"],
                (
                    f"Unit {row['Unit']}: "
                    f"{_text(item.reason)}"
                ),
            )

        # ==============================================
        # LEASE HISTORY
        # ==============================================

        lease_rows = []

        for lease in leases:

            row = {
                "Lease ID": lease.id,
                "Unit": unit(
                    lease.apartment_id
                ),
                "Start": lease.start_date,
                "End": lease.end_date,
                "Status": (
                    _text(lease.status).title()
                ),
                "Monthly Rent": _money(
                    lease.monthly_rent
                ),
                "Security Deposit": _money(
                    lease.security_deposit
                ),
            }

            lease_rows.append(row)

            add_event(
                lease.start_date,
                "Lease",
                "Lease effective date",
                (
                    f"Lease #{lease.id}, "
                    f"Unit {row['Unit']}, "
                    f"current status: {row['Status']}"
                ),
            )

        # ==============================================
        # LEASE RENEWALS
        # ==============================================

        renewal_rows = []

        for item in renewals:

            row = {
                "Renewal ID": item.id,
                "Lease ID": item.lease_id,
                "Unit": unit(
                    item.apartment_id
                ),
                "Previous End": (
                    item.previous_end_date
                ),
                "New End": item.new_end_date,
                "Monthly Rent": _money(
                    item.monthly_rent
                ),
                "Notes": _text(item.notes),
                "Admin ID": item.admin_user_id,
                "Recorded At": item.created_at,
            }

            renewal_rows.append(row)

            add_event(
                item.created_at,
                "Lease",
                "Lease renewed",
                (
                    f"Lease #{item.lease_id}: "
                    f"{item.previous_end_date} → "
                    f"{item.new_end_date}. "
                    f"{_text(item.notes)}"
                ),
            )

        # ==============================================
        # APARTMENT TRANSFERS
        # ==============================================

        transfer_rows = []

        for item in transfers:

            row = {
                "Transfer ID": item.id,
                "Effective": (
                    item.effective_date
                ),
                "From": (
                    item.previous_unit_number
                ),
                "To": (
                    item.new_unit_number
                ),
                "Old Lease": (
                    item.previous_lease_id
                ),
                "New Lease": item.new_lease_id,
                "Reason": item.reason,
                "Admin ID": item.admin_user_id,
            }

            transfer_rows.append(row)

            add_event(
                item.effective_date,
                "Apartment Transfer",
                "Apartment transferred",
                (
                    f"Unit {item.previous_unit_number} "
                    f"→ Unit {item.new_unit_number}. "
                    f"{item.reason}"
                ),
            )

        # ==============================================
        # RENT PAYMENT HISTORY
        # ==============================================

        payment_rows = []

        confirmed_total = Decimal(
            "0.00"
        )

        for item in payments:

            status = _text(
                item.status
            )

            amount = _money(
                item.amount
            )

            if (
                status.casefold()
                in CONFIRMED_PAYMENT_STATUSES
            ):
                confirmed_total += amount

            row = {
                "Payment ID": item.id,
                "Lease ID": _value(
                    item,
                    "lease_id",
                ),
                "Unit": lease_unit.get(
                    _value(item, "lease_id"),
                    "—",
                ),
                "Payment Month": _value(
                    item,
                    "payment_month",
                ),
                "Amount": amount,
                "Status": status,
                "Method": _text(
                    _value(
                        item,
                        "payment_method",
                    )
                ),
                "Reference": _text(
                    _value(
                        item,
                        "confirmation_number",
                    )
                ),
                "Paid At": _value(
                    item,
                    "paid_at",
                ),
            }

            payment_rows.append(row)

            add_event(
                _value(
                    item,
                    "paid_at",
                    "created_at",
                    "payment_month",
                ),
                "Payment",
                f"Payment {status.lower()}",
                (
                    f"Payment #{item.id}; "
                    f"lease #"
                    f"{_value(item, 'lease_id', default='—')}; "
                    f"reference {row['Reference']}"
                ),
                amount,
            )

        # ==============================================
        # MAINTENANCE REQUEST HISTORY
        # ==============================================

        maintenance_rows = []

        for item in maintenance:

            row = {
                "Request ID": item.id,
                "Unit": unit(
                    _value(
                        item,
                        "apartment_id",
                    )
                ),
                "Category": _text(
                    _value(
                        item,
                        "category",
                        "request_type",
                        "issue_type",
                        "type",
                    )
                ),
                "Description": _text(
                    _value(
                        item,
                        "description",
                        "details",
                        "title",
                    )
                ),
                "Priority": _text(
                    _value(
                        item,
                        "priority",
                        "urgency",
                    )
                ),
                "Status": _text(
                    _value(
                        item,
                        "status",
                    )
                ),
                "Created": _value(
                    item,
                    "created_at",
                    "submitted_at",
                ),
            }

            maintenance_rows.append(row)

            add_event(
                row["Created"],
                "Maintenance",
                "Maintenance request submitted",
                (
                    f"Request #{item.id}: "
                    f"{row['Description']}"
                ),
            )

        # ==============================================
        # MAINTENANCE UPDATES
        # ==============================================

        maintenance_update_rows = []

        for item in updates:

            request_id = getattr(
                item,
                update_parent_field,
            )

            row = {
                "Update ID": item.id,
                "Request ID": request_id,
                "Status": _text(
                    _value(
                        item,
                        "new_status",
                        "status",
                    )
                ),
                "Details": _text(
                    _value(
                        item,
                        "notes",
                        "message",
                        "description",
                        "update_text",
                    )
                ),
                "Recorded At": _value(
                    item,
                    "created_at",
                    "updated_at",
                ),
            }

            maintenance_update_rows.append(row)

            add_event(
                row["Recorded At"],
                "Maintenance",
                "Maintenance updated",
                (
                    f"Request #{request_id}, "
                    f"status {row['Status']}: "
                    f"{row['Details']}"
                ),
            )

        # ==============================================
        # MOVE-OUT INSPECTIONS
        # ==============================================

        inspection_rows = []

        for item in inspections:

            row = {
                "Inspection ID": item.id,
                "Unit": unit(
                    item.apartment_id
                ),
                "Source": (
                    _text(item.source)
                    .replace("_", " ")
                    .title()
                ),
                "Status": (
                    _text(item.status).title()
                ),
                "Inspection Date": (
                    item.inspection_date
                ),
                "Cleanliness": _text(
                    item.cleanliness
                ),
                "Walls / Floors": _text(
                    item.walls_floors
                ),
                "Appliances": _text(
                    item.appliances
                ),
                "Estimated Repairs": _money(
                    item.estimated_repair_cost
                ),
                "Damage Notes": _text(
                    item.damage_notes
                ),
                "Inspection Notes": _text(
                    item.inspection_notes
                ),
                "Approved At": (
                    item.approved_at
                ),
            }

            inspection_rows.append(row)

            add_event(
                item.created_at,
                "Inspection",
                "Inspection hold created",
                (
                    f"Unit {row['Unit']}, "
                    f"source {row['Source']}"
                ),
            )

            add_event(
                item.inspected_at,
                "Inspection",
                "Inspection documented",
                (
                    f"Unit {row['Unit']}, "
                    f"estimated repairs "
                    f"${row['Estimated Repairs']:,.2f} "
                    f"(not a deduction)"
                ),
            )

            add_event(
                item.approved_at,
                "Inspection",
                "Unit released after inspection",
                f"Unit {row['Unit']}",
            )

        # ==============================================
        # SECURITY DEPOSIT DEDUCTIONS
        # ==============================================

        deduction_by_settlement = {}

        for deduction in deductions:

            deduction_by_settlement.setdefault(
                deduction.settlement_id,
                [],
            ).append(
                {
                    "Category": (
                        deduction.category
                    ),
                    "Description": (
                        deduction.description
                    ),
                    "Amount": _money(
                        deduction.amount
                    ),
                }
            )

        # ==============================================
        # SECURITY DEPOSIT SETTLEMENTS
        # ==============================================

        deposit_rows = []

        for item in deposits:

            row = {
                "Settlement ID": item.id,
                "Lease ID": item.lease_id,
                "Unit": unit(
                    item.apartment_id
                ),
                "Deposit": _money(
                    item.deposit_amount
                ),
                "Approved Deductions": _money(
                    item.approved_deductions
                ),
                "Approved Refund": _money(
                    item.approved_refund
                ),
                "Status": (
                    _text(item.status)
                    .replace("_", " ")
                    .title()
                ),
                "Refund Method": _text(
                    item.refund_method
                ),
                "Refund Reference": _text(
                    item.refund_reference
                ),
                "Refunded On": (
                    item.refunded_on
                ),
                "Notes": _text(
                    item.notes
                ),
            }

            deposit_rows.append(row)

            add_event(
                item.created_at,
                "Security Deposit",
                "Deposit settlement opened",
                (
                    f"Settlement #{item.id}; "
                    f"recorded deposit "
                    f"${row['Deposit']:,.2f}"
                ),
            )

        # ==============================================
        # DEPOSIT SETTLEMENT AUDIT EVENTS
        # ==============================================

        for item in deposit_events:

            add_event(
                item.created_at,
                "Security Deposit",
                (
                    _text(item.action)
                    .replace("_", " ")
                    .title()
                ),
                (
                    f"Settlement #{item.settlement_id}: "
                    f"{item.details}"
                ),
            )

        # ==============================================
        # SORT ACTIVITY — NEWEST FIRST
        # ==============================================

        events.sort(
            key=lambda row: _sort_date(
                row["date"]
            ),
            reverse=True,
        )

        # ==============================================
        # BUILD FINAL HISTORY RESULT
        # ==============================================

        return {
            "resident": {
                "id": resident.id,
                "name": resident.full_name,
                "email": resident.email,
                "phone": _text(
                    _value(
                        resident,
                        "phone",
                    )
                ),
                "status": (
                    "Active"
                    if resident.is_active
                    else "Archived / Inactive"
                ),
                "current_unit": current_unit,
                "joined": _value(
                    resident,
                    "created_at",
                ),
            },
            "summary": {
                "leases": len(leases),
                "transfers": len(transfers),
                "payments": len(payments),
                "confirmed_payments": confirmed_total,
                "maintenance": len(maintenance),
                "inspections": len(inspections),
                "settlements": len(deposits),
                "events": len(events),
            },
            "leases": lease_rows,
            "renewals": renewal_rows,
            "transfers": transfer_rows,
            "payments": payment_rows,
            "maintenance": maintenance_rows,
            "maintenance_updates": maintenance_update_rows,
            "inspections": inspection_rows,
            "deposits": deposit_rows,
            "deductions_by_settlement": (
                deduction_by_settlement
            ),
            "tenancy_events": tenancy_rows,
            "timeline": events,
        }
