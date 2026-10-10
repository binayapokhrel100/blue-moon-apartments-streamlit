from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from core.security import verify_password
from database.db import get_db_session
from database.models import User


def authenticate_user(
    email: str,
    password: str,
) -> User | None:

    cleaned_email = email.strip().lower()

    if not cleaned_email or not password:
        return None

    with get_db_session() as db:

        statement = (
            select(User)
            .options(
                joinedload(User.apartment)
            )
            .where(
                func.lower(User.email)
                == cleaned_email
            )
        )

        user = db.scalar(statement)

        if user is None:
            return None

        if not user.is_active:
            return None

        if not verify_password(
            password,
            user.password_hash,
        ):
            return None

        user.last_login_at = datetime.utcnow()

        db.flush()

        return user


def get_user_by_id(
    user_id: int,
) -> User | None:

    with get_db_session() as db:

        statement = (
            select(User)
            .options(
                joinedload(User.apartment)
            )
            .where(
                User.id == user_id
            )
        )

        return db.scalar(statement)