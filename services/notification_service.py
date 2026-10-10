from datetime import datetime

from sqlalchemy import func, select

from database.db import get_db_session
from database.models import Notification


def create_notification(
    user_id: int,
    title: str,
    message: str,
    notification_type: str = "general",
    is_alert: bool = False,
) -> dict:

    with get_db_session() as db:

        notification = Notification(
            user_id=user_id,
            title=title,
            message=message,
            notification_type=notification_type,
            is_read=False,
            is_alert=is_alert,
        )

        db.add(notification)
        db.flush()

        return _notification_to_dict(notification)


def get_notifications_for_user(
    user_id: int,
) -> list[dict]:

    with get_db_session() as db:

        statement = (
            select(Notification)
            .where(
                Notification.user_id == user_id
            )
            .order_by(
                Notification.created_at.desc()
            )
        )

        notifications = db.scalars(
            statement
        ).all()

        return [
            _notification_to_dict(notification)
            for notification in notifications
        ]


def get_unread_count(
    user_id: int,
) -> int:

    with get_db_session() as db:

        statement = (
            select(
                func.count(Notification.id)
            )
            .where(
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
            )
        )

        return int(
            db.scalar(statement) or 0
        )


def mark_notification_read(
    notification_id: int,
    user_id: int,
) -> bool:

    with get_db_session() as db:

        statement = (
            select(Notification)
            .where(
                Notification.id
                == notification_id,

                Notification.user_id
                == user_id,
            )
        )

        notification = db.scalar(
            statement
        )

        if notification is None:
            return False

        notification.is_read = True

        return True


def mark_all_notifications_read(
    user_id: int,
) -> int:

    with get_db_session() as db:

        statement = (
            select(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
            )
        )

        notifications = db.scalars(
            statement
        ).all()

        updated = 0

        for notification in notifications:
            notification.is_read = True
            updated += 1

        return updated


def _notification_to_dict(
    notification: Notification,
) -> dict:

    return {
        "id": notification.id,
        "user_id": notification.user_id,
        "title": notification.title,
        "message": notification.message,
        "notification_type": (
            notification.notification_type
        ),
        "is_read": notification.is_read,
        "is_alert": notification.is_alert,
        "created_at": notification.created_at,
    }