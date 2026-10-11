from datetime import datetime
from secrets import randbelow

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database.db import get_db_session
from database.models import (
    MaintenanceRequest,
    MaintenanceUpdate,
    Notification,
    User,
)


VALID_CATEGORIES = {
    "Plumbing",
    "Electrical",
    "HVAC",
    "Appliance",
    "Pest Control",
    "Door / Lock",
    "General Repair",
    "Other",
}


VALID_URGENCIES = {
    "Low",
    "Medium",
    "High",
    "Emergency",
}


VALID_STATUSES = {
    "Submitted",
    "Scheduled",
    "In Progress",
    "Completed",
    "Cancelled",
}


def generate_request_number(
    year: int | None = None,
) -> str:

    if year is None:
        year = datetime.now().year

    sequence = randbelow(9000) + 1000

    return (
        f"MR-{year}-{sequence:04d}"
    )


def validate_maintenance_request(
    category: str,
    description: str,
    urgency: str,
) -> None:

    if category not in VALID_CATEGORIES:
        raise ValueError(
            "Please select a valid maintenance category."
        )

    cleaned_description = description.strip()

    if len(cleaned_description) < 10:
        raise ValueError(
            "Please provide at least 10 characters "
            "describing the maintenance issue."
        )

    if urgency not in VALID_URGENCIES:
        raise ValueError(
            "Please select a valid urgency level."
        )


def _create_unique_request_number(
    db,
) -> str:

    for _ in range(20):

        request_number = (
            generate_request_number()
        )

        existing = db.scalar(
            select(
                MaintenanceRequest.id
            ).where(
                MaintenanceRequest.request_number
                == request_number
            )
        )

        if existing is None:
            return request_number

    raise RuntimeError(
        "Unable to generate a unique "
        "maintenance request number."
    )


def create_maintenance_request(
    user_id: int,
    category: str,
    description: str,
    urgency: str,
    location_detail: str = "",
) -> dict:

    validate_maintenance_request(
        category=category,
        description=description,
        urgency=urgency,
    )

    with get_db_session() as db:

        user = db.get(
            User,
            user_id,
        )

        if user is None:
            raise ValueError(
                "Resident account was not found."
            )

        if user.apartment_id is None:
            raise ValueError(
                "No apartment is assigned "
                "to this resident."
            )

        request_number = (
            _create_unique_request_number(
                db
            )
        )

        request = MaintenanceRequest(
            request_number=request_number,
            resident_id=user.id,
            apartment_id=user.apartment_id,
            category=category,
            location_detail=(
                location_detail.strip()
                or None
            ),
            description=description.strip(),
            urgency=urgency,
            status="Submitted",
        )

        db.add(request)
        db.flush()

        initial_update = MaintenanceUpdate(
            request_id=request.id,
            status="Submitted",
            message=(
                "Maintenance request submitted "
                "by resident."
            ),
        )

        db.add(initial_update)

        notification = Notification(
            user_id=user.id,
            title=(
                "Maintenance Request Submitted "
                f"— {request_number}"
            ),
            message=(
                f"Your {category.lower()} "
                "maintenance request has been "
                "submitted successfully. "
                "We will notify you when the "
                "status changes."
            ),
            notification_type="maintenance",
            is_read=False,
            is_alert=False,
        )

        db.add(notification)
        db.flush()

        return _request_to_dict(
            request
        )


def get_maintenance_requests_for_user(
    user_id: int,
) -> list[dict]:

    with get_db_session() as db:

        statement = (
            select(MaintenanceRequest)
            .where(
                MaintenanceRequest.resident_id
                == user_id
            )
            .order_by(
                MaintenanceRequest.created_at.desc()
            )
        )

        requests = db.scalars(
            statement
        ).all()

        return [
            _request_to_dict(request)
            for request in requests
        ]


def get_maintenance_request_detail(
    request_id: int,
    user_id: int,
) -> dict | None:

    with get_db_session() as db:

        statement = (
            select(MaintenanceRequest)
            .options(
                selectinload(
                    MaintenanceRequest.updates
                )
            )
            .where(
                MaintenanceRequest.id
                == request_id,
                MaintenanceRequest.resident_id
                == user_id,
            )
        )

        request = db.scalar(
            statement
        )

        if request is None:
            return None

        result = _request_to_dict(
            request
        )

        ordered_updates = sorted(
            request.updates,
            key=lambda item: item.created_at,
            reverse=True,
        )

        result["updates"] = [
            {
                "id": update.id,
                "status": update.status,
                "message": update.message,
                "created_at": (
                    update.created_at
                ),
            }
            for update in ordered_updates
        ]

        return result


def add_maintenance_update(
    request_id: int,
    status: str,
    message: str,
    technician_name: str | None = None,
    scheduled_start: datetime | None = None,
    scheduled_end: datetime | None = None,
) -> dict:

    if status not in VALID_STATUSES:
        raise ValueError(
            "Invalid maintenance status."
        )

    if not message.strip():
        raise ValueError(
            "Maintenance update message "
            "cannot be empty."
        )

    with get_db_session() as db:

        request = db.get(
            MaintenanceRequest,
            request_id,
        )

        if request is None:
            raise ValueError(
                "Maintenance request was not found."
            )

        request.status = status
        request.updated_at = datetime.utcnow()

        if technician_name is not None:
            request.technician_name = (
                technician_name.strip()
                or None
            )

        if scheduled_start is not None:
            request.scheduled_start = (
                scheduled_start
            )

        if scheduled_end is not None:
            request.scheduled_end = (
                scheduled_end
            )

        update = MaintenanceUpdate(
            request_id=request.id,
            status=status,
            message=message.strip(),
        )

        db.add(update)

        notification_title = (
            _notification_title(
                request.request_number,
                status,
            )
        )

        notification = Notification(
            user_id=request.resident_id,
            title=notification_title,
            message=message.strip(),
            notification_type="maintenance",
            is_read=False,
            is_alert=False,
        )

        db.add(notification)
        db.flush()

        return _request_to_dict(
            request
        )


def _notification_title(
    request_number: str,
    status: str,
) -> str:

    if status == "Scheduled":
        return (
            "Maintenance Scheduled — "
            f"{request_number}"
        )

    if status == "In Progress":
        return (
            "Maintenance Update — "
            f"{request_number}"
        )

    if status == "Completed":
        return (
            "Maintenance Completed — "
            f"{request_number}"
        )

    return (
        "Maintenance Update — "
        f"{request_number}"
    )


def _request_to_dict(
    request: MaintenanceRequest,
) -> dict:

    return {
        "id": request.id,
        "request_number": (
            request.request_number
        ),
        "resident_id": request.resident_id,
        "apartment_id": request.apartment_id,
        "category": request.category,
        "location_detail": (
            request.location_detail
        ),
        "description": request.description,
        "urgency": request.urgency,
        "status": request.status,
        "technician_name": (
            request.technician_name
        ),
        "scheduled_start": (
            request.scheduled_start
        ),
        "scheduled_end": (
            request.scheduled_end
        ),
        "created_at": request.created_at,
        "updated_at": request.updated_at,
    }