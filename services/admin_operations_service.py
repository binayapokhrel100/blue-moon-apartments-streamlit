
"""Admin payment reporting and maintenance workflows for Sprint 09.

Payments are read-only. Maintenance updates and notifications are transactional.
"""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from database.db import get_db_session
from database.models import (
    AdminEmployee,
    MaintenanceRequest,
    MaintenanceUpdate,
    Notification,
    Payment,
    User,
)


# ==================================================
# MAINTENANCE STATUS DEFINITIONS
# ==================================================

MAINTENANCE_STATUSES = (
    "Submitted",
    "Scheduled",
    "In Progress",
    "Completed",
    "Cancelled",
)

MAINTENANCE_TRANSITIONS = {
    "Submitted": {
        "Scheduled",
        "In Progress",
        "Cancelled",
    },
    "Scheduled": {
        "In Progress",
        "Cancelled",
    },
    "In Progress": {
        "Completed",
        "Cancelled",
    },
    "Completed": set(),
    "Cancelled": set(),
}


# ==================================================
# DATE HELPER
# ==================================================

def _now_utc() -> datetime:
    """Return UTC time matching the existing database convention."""

    return datetime.now(timezone.utc).replace(
        tzinfo=None
    )


# ==================================================
# ADMIN AUTHORIZATION
# ==================================================

def _require_admin(
    db,
    admin_user_id: int,
    permission: str,
) -> None:
    """Use the central database-backed role check."""
    from services.admin_management_service import (
        _require_admin as shared_admin_check,
    )
    shared_admin_check(
        db,
        admin_user_id,
        permission=permission,
    )


# ==================================================
# ADMIN PAYMENT REPORTING
# ==================================================

def get_admin_payments(
    admin_user_id: int,
) -> dict:
    """Return payment summaries and the latest 200 records."""

    now = _now_utc()

    start = datetime(
        now.year,
        now.month,
        1,
    )

    if now.month == 12:
        end = datetime(
            now.year + 1,
            1,
            1,
        )
    else:
        end = datetime(
            now.year,
            now.month + 1,
            1,
        )

    with get_db_session() as db:

        _require_admin(
            db,
            admin_user_id,
            permission="payments.read",
        )

        # --------------------------------------
        # TOTAL PAYMENT RECORDS
        # --------------------------------------

        total = db.scalar(
            select(
                func.count(Payment.id)
            )
        ) or 0

        # --------------------------------------
        # CONFIRMED PAYMENT COUNT
        # --------------------------------------

        confirmed_count = db.scalar(
            select(
                func.count(Payment.id)
            ).where(
                func.lower(Payment.status)
                == "confirmed"
            )
        ) or 0

        # --------------------------------------
        # TOTAL CONFIRMED COLLECTIONS
        # --------------------------------------

        confirmed_total = db.scalar(
            select(
                func.sum(Payment.amount)
            ).where(
                func.lower(Payment.status)
                == "confirmed"
            )
        ) or Decimal("0.00")

        # --------------------------------------
        # CURRENT MONTH COLLECTIONS
        # --------------------------------------

        collected_this_month = db.scalar(
            select(
                func.sum(Payment.amount)
            ).where(
                func.lower(Payment.status)
                == "confirmed",
                Payment.paid_at >= start,
                Payment.paid_at < end,
            )
        ) or Decimal("0.00")

        # --------------------------------------
        # RECENT PAYMENT RECORDS
        # --------------------------------------

        records = db.scalars(
            select(Payment)
            .options(
                joinedload(Payment.resident)
            )
            .order_by(
                Payment.paid_at.desc(),
                Payment.id.desc(),
            )
            .limit(200)
        ).all()

        payments = []

        for item in records:

            resident_name = (
                item.resident.full_name
                if item.resident
                else "Unknown"
            )

            resident_email = (
                item.resident.email
                if item.resident
                else ""
            )

            payments.append(
                {
                    "id": item.id,
                    "resident": resident_name,
                    "email": resident_email,
                    "amount": item.amount,
                    "month": item.payment_month,
                    "method": item.payment_method,
                    "status": item.status,
                    "confirmation": (
                        item.confirmation_number
                    ),
                    "paid_at": item.paid_at,
                }
            )

    return {
        "total_records": int(total),
        "confirmed_records": int(
            confirmed_count
        ),
        "confirmed_total": confirmed_total,
        "collected_this_month": (
            collected_this_month
        ),
        "month_label": start.strftime(
            "%B %Y"
        ),
        "payments": payments,
    }


# ==================================================
# ADMIN MAINTENANCE REPORTING
# ==================================================

def get_admin_maintenance(
    admin_user_id: int,
) -> dict:
    """Return maintenance summaries and recent requests."""

    with get_db_session() as db:

        _require_admin(
            db,
            admin_user_id,
            permission="maintenance.read",
        )

        # --------------------------------------
        # ALL REQUESTS
        # --------------------------------------

        total = db.scalar(
            select(
                func.count(
                    MaintenanceRequest.id
                )
            )
        ) or 0

        # --------------------------------------
        # OPEN REQUESTS
        # --------------------------------------

        open_count = db.scalar(
            select(
                func.count(
                    MaintenanceRequest.id
                )
            ).where(
                func.lower(
                    func.trim(
                        MaintenanceRequest.status
                    )
                ).not_in(
                    (
                        "completed",
                        "cancelled",
                        "canceled",
                    )
                )
            )
        ) or 0

        # --------------------------------------
        # COMPLETED REQUESTS
        # --------------------------------------

        completed = db.scalar(
            select(
                func.count(
                    MaintenanceRequest.id
                )
            ).where(
                func.lower(
                    func.trim(
                        MaintenanceRequest.status
                    )
                ) == "completed"
            )
        ) or 0

        # --------------------------------------
        # RECENT REQUEST RECORDS
        # --------------------------------------

        records = db.scalars(
            select(MaintenanceRequest)
            .options(
                joinedload(
                    MaintenanceRequest.resident
                ),
                joinedload(
                    MaintenanceRequest.apartment
                ),
            )
            .order_by(
                MaintenanceRequest.created_at.desc(),
                MaintenanceRequest.id.desc(),
            )
            .limit(200)
        ).all()

        requests = []

        for item in records:

            requests.append(
                {
                    "id": item.id,
                    "number": item.request_number,
                    "resident": (
                        item.resident.full_name
                        if item.resident
                        else "Unknown"
                    ),
                    "unit": (
                        item.apartment.unit_number
                        if item.apartment
                        else "—"
                    ),
                    "category": item.category,
                    "location": (
                        item.location_detail
                        or "—"
                    ),
                    "description": (
                        item.description
                    ),
                    "urgency": item.urgency,
                    "status": item.status,
                    "technician": (
                        item.technician_name
                        or ""
                    ),
                    "start": (
                        item.scheduled_start
                    ),
                    "end": (
                        item.scheduled_end
                    ),
                    "created_at": (
                        item.created_at
                    ),
                    "updated_at": (
                        item.updated_at
                    ),
                }
            )

    return {
        "total": int(total),
        "open": int(open_count),
        "completed": int(completed),
        "requests": requests,
    }


# ==================================================
# MAINTENANCE HISTORY
# ==================================================

def get_maintenance_history(
    admin_user_id: int,
    request_id: int,
) -> list[dict]:
    """Retrieve the latest maintenance status notes."""

    with get_db_session() as db:

        _require_admin(
            db,
            admin_user_id,
            permission="maintenance.read",
        )

        request = db.get(
            MaintenanceRequest,
            request_id,
        )

        if request is None:
            raise ValueError(
                "Maintenance request not found."
            )

        records = db.scalars(
            select(MaintenanceUpdate)
            .where(
                MaintenanceUpdate.request_id
                == request_id
            )
            .order_by(
                MaintenanceUpdate.created_at.desc(),
                MaintenanceUpdate.id.desc(),
            )
            .limit(25)
        ).all()

        return [
            {
                "status": record.status,
                "message": record.message,
                "at": record.created_at,
            }
            for record in records
        ]


# ==================================================
# UPDATE MAINTENANCE REQUEST
# ==================================================

def update_maintenance_request(
    admin_user_id: int,
    request_id: int,
    *,
    expected_status: str,
    new_status: str,
    technician_name: str,
    note: str,
    scheduled_start: datetime | None = None,
    scheduled_end: datetime | None = None,
) -> None:
    """
    Update a maintenance request and create:
    1. Maintenance history entry
    2. Resident notification

    All changes use the same database transaction.
    """

    technician = (
        technician_name or ""
    ).strip()

    message = (
        note or ""
    ).strip()

    # --------------------------------------
    # VALIDATE USER INPUT
    # --------------------------------------

    if len(technician) > 150:
        raise ValueError(
            "Technician name must be "
            "150 characters or fewer."
        )

    if len(message) > 500:
        raise ValueError(
            "Update note must be "
            "500 characters or fewer."
        )

    if new_status not in MAINTENANCE_STATUSES:
        raise ValueError(
            "Unsupported maintenance status."
        )

    with get_db_session() as db:

        _require_admin(
            db,
            admin_user_id,
            permission="maintenance.update",
        )

        request = db.get(
            MaintenanceRequest,
            request_id,
        )

        if request is None:
            raise ValueError(
                "Maintenance request not found."
            )

        old_status = str(
            request.status or ""
        ).strip()

        # --------------------------------------
        # CHECK CONCURRENT STATUS CHANGE
        # --------------------------------------

        if old_status != expected_status:
            raise ValueError(
                "This request was updated elsewhere. "
                "Refresh and try again."
            )

        if (
            old_status
            not in MAINTENANCE_TRANSITIONS
        ):
            raise ValueError(
                "This request has an unsupported "
                "current status."
            )

        # --------------------------------------
        # ENFORCE STATUS WORKFLOW
        # --------------------------------------

        status_changed = (
            new_status != old_status
        )

        if (
            status_changed
            and new_status not in
            MAINTENANCE_TRANSITIONS[old_status]
        ):
            raise ValueError(
                f"Cannot change status from "
                f"{old_status} to {new_status}."
            )

        if (
            not status_changed
            and old_status in (
                "Completed",
                "Cancelled",
            )
        ):
            raise ValueError(
                "Completed or cancelled requests "
                "are read-only."
            )

        # --------------------------------------
        # VALIDATE APPOINTMENT
        # --------------------------------------

        start_changed = False

        if new_status == "Scheduled":

            if (
                scheduled_start is None
                or scheduled_end is None
            ):
                raise ValueError(
                    "Provide the appointment "
                    "start and end times."
                )

            if (
                scheduled_end
                <= scheduled_start
            ):
                raise ValueError(
                    "Appointment end must be "
                    "after the start."
                )

            start_changed = (
                request.scheduled_start
                != scheduled_start
                or request.scheduled_end
                != scheduled_end
            )

        elif (
            scheduled_start is not None
            or scheduled_end is not None
        ):
            raise ValueError(
                "Appointment times may only "
                "be changed while Scheduled."
            )

        # --------------------------------------
        # DETECT CHANGES
        # --------------------------------------

        technician_changed = (
            (
                request.technician_name
                or ""
            ).strip() != technician
        )

        if not (
            status_changed
            or technician_changed
            or start_changed
            or message
        ):
            raise ValueError(
                "No changes to save. "
                "Add a note or update a field."
            )

        if status_changed and not message:
            raise ValueError(
                "Please add a short note "
                "explaining the status change."
            )

        # --------------------------------------
        # SAVE REQUEST
        # --------------------------------------

        request.status = new_status

        request.technician_name = (
            technician or None
        )

        if new_status == "Scheduled":
            request.scheduled_start = (
                scheduled_start
            )

            request.scheduled_end = (
                scheduled_end
            )

        if not message:
            message = (
                "Maintenance assignment or "
                "appointment updated."
            )

        # --------------------------------------
        # SAVE MAINTENANCE HISTORY
        # --------------------------------------

        db.add(
            MaintenanceUpdate(
                request_id=request.id,
                status=new_status,
                message=message,
            )
        )

        # --------------------------------------
        # NOTIFY THE RESIDENT
        # --------------------------------------

        notification_message = (
            f"Request {request.request_number} "
            f"is {new_status}. {message}"
        )

        db.add(
            Notification(
                user_id=request.resident_id,
                title=(
                    "Maintenance Update — "
                    f"{request.request_number}"
                ),
                message=(
                    notification_message[:1000]
                ),
                notification_type="maintenance",
                is_read=False,
                is_alert=False,
            )
        )

        db.flush()
