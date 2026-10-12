from datetime import datetime

from sqlalchemy import select

from core.security import (
    hash_password,
    verify_password,
)
from database.db import get_db_session
from database.models import (
    LoginEvent,
    Notification,
    User,
)


def validate_new_password(
    new_password: str,
    confirm_password: str,
) -> None:

    if new_password != confirm_password:
        raise ValueError(
            "New password and confirmation "
            "do not match."
        )

    if len(new_password) < 12:
        raise ValueError(
            "Password must contain at least "
            "12 characters."
        )

    if not any(
        char.isupper()
        for char in new_password
    ):
        raise ValueError(
            "Password must contain at least "
            "one uppercase letter."
        )

    if not any(
        char.islower()
        for char in new_password
    ):
        raise ValueError(
            "Password must contain at least "
            "one lowercase letter."
        )

    if not any(
        char.isdigit()
        for char in new_password
    ):
        raise ValueError(
            "Password must contain at least "
            "one number."
        )

    special_characters = (
        "!@#$%^&*()-_=+[]{};:,.?"
    )

    if not any(
        char in special_characters
        for char in new_password
    ):
        raise ValueError(
            "Password must contain at least "
            "one special character."
        )


def record_successful_login(
    user_id: int,
    client_info: dict,
) -> dict:

    device_name = (
        client_info.get(
            "device_name"
        )
        or "Unknown Device"
    )

    browser_name = (
        client_info.get(
            "browser_name"
        )
        or "Unknown Browser"
    )

    ip_address = (
        client_info.get(
            "ip_address"
        )
        or "Unavailable"
    )

    location_label = (
        client_info.get(
            "location_label"
        )
        or "Unavailable"
    )

    user_agent = (
        client_info.get(
            "user_agent"
        )
        or ""
    )

    with get_db_session() as db:

        previous_logins = db.scalars(
            select(LoginEvent)
            .where(
                LoginEvent.user_id
                == user_id,

                LoginEvent.event_type
                == "login_success",

                LoginEvent.success.is_(
                    True
                ),
            )
            .order_by(
                LoginEvent.created_at.desc()
            )
        ).all()

        comparable_device = (
            device_name
            != "Unknown Device"
            and browser_name
            != "Unknown Browser"
        )

        known_device = any(
            event.device_name
            == device_name
            and event.browser_name
            == browser_name

            for event
            in previous_logins
        )

        is_new_device = (
            bool(previous_logins)
            and comparable_device
            and not known_device
        )

        event = LoginEvent(
            user_id=user_id,
            event_type="login_success",
            success=True,
            device_name=device_name,
            browser_name=browser_name,
            ip_address=ip_address,
            location_label=(
                location_label
            ),
            user_agent=user_agent,
        )

        db.add(event)
        db.flush()

        if is_new_device:

            db.add(
                Notification(
                    user_id=user_id,
                    title=(
                        "New Login Detected"
                    ),
                    message=(
                        "A new login to your "
                        "account was detected "
                        f"from {device_name} — "
                        f"{browser_name}. "
                        "If this was not you, "
                        "please change your "
                        "password immediately."
                    ),
                    notification_type=(
                        "security"
                    ),
                    is_read=False,
                    is_alert=True,
                )
            )

        db.flush()

        return {
            "id": event.id,
            "event_type": (
                event.event_type
            ),
            "success": event.success,
            "device_name": (
                event.device_name
            ),
            "browser_name": (
                event.browser_name
            ),
            "ip_address": (
                event.ip_address
            ),
            "location_label": (
                event.location_label
            ),
            "created_at": (
                event.created_at
            ),
            "is_new_device": (
                is_new_device
            ),
        }


def get_login_events(
    user_id: int,
    limit: int = 10,
) -> list[dict]:

    with get_db_session() as db:

        statement = (
            select(LoginEvent)
            .where(
                LoginEvent.user_id
                == user_id
            )
            .order_by(
                LoginEvent.created_at.desc()
            )
            .limit(limit)
        )

        events = db.scalars(
            statement
        ).all()

        return [
            _event_to_dict(event)
            for event in events
        ]


def get_security_summary(
    user_id: int,
) -> dict:

    events = get_login_events(
        user_id=user_id,
        limit=20,
    )

    successful_logins = [
        event
        for event in events
        if (
            event["event_type"]
            == "login_success"
            and event["success"]
        )
    ]

    password_changes = [
        event
        for event in events
        if event["event_type"]
        == "password_changed"
    ]

    last_password_change = (
        password_changes[0][
            "created_at"
        ]
        if password_changes
        else None
    )

    last_login = (
        successful_logins[0][
            "created_at"
        ]
        if successful_logins
        else None
    )

    return {
        "recent_login_count": len(
            successful_logins
        ),
        "last_login": last_login,
        "last_password_change": (
            last_password_change
        ),
    }


def change_password(
    user_id: int,
    current_password: str,
    new_password: str,
    confirm_password: str,
    client_info: dict | None = None,
) -> None:

    validate_new_password(
        new_password,
        confirm_password,
    )

    with get_db_session() as db:

        user = db.get(
            User,
            user_id,
        )

        if user is None:
            raise ValueError(
                "Resident account "
                "was not found."
            )

        if not verify_password(
            current_password,
            user.password_hash,
        ):
            raise ValueError(
                "Current password is incorrect."
            )

        if verify_password(
            new_password,
            user.password_hash,
        ):
            raise ValueError(
                "New password must be "
                "different from your "
                "current password."
            )

        user.password_hash = (
            hash_password(
                new_password
            )
        )

        metadata = (
            client_info
            or {}
        )

        event = LoginEvent(
            user_id=user.id,
            event_type=(
                "password_changed"
            ),
            success=True,
            device_name=metadata.get(
                "device_name",
                "Unknown Device",
            ),
            browser_name=metadata.get(
                "browser_name",
                "Unknown Browser",
            ),
            ip_address=metadata.get(
                "ip_address",
                "Unavailable",
            ),
            location_label=metadata.get(
                "location_label",
                "Unavailable",
            ),
            user_agent=metadata.get(
                "user_agent",
                "",
            ),
        )

        db.add(event)

        notification = Notification(
            user_id=user.id,
            title="Password Changed",
            message=(
                "Your Blue Moon account "
                "password was successfully "
                "changed. If you did not "
                "make this change, contact "
                "property management immediately."
            ),
            notification_type="security",
            is_read=False,
            is_alert=True,
        )

        db.add(notification)


def _event_to_dict(
    event: LoginEvent,
) -> dict:

    return {
        "id": event.id,
        "event_type": (
            event.event_type
        ),
        "success": event.success,
        "device_name": (
            event.device_name
            or "Unknown Device"
        ),
        "browser_name": (
            event.browser_name
            or "Unknown Browser"
        ),
        "ip_address": (
            event.ip_address
            or "Unavailable"
        ),
        "location_label": (
            event.location_label
            or "Unavailable"
        ),
        "created_at": (
            event.created_at
        ),
    }