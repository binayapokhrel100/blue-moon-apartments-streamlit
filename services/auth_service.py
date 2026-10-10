from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from core.security import verify_password
from database.db import get_db_session
from database.models import User


def authenticate_user(
    email: str,
    password: str,
) -> User | None:
    """Authenticate a resident using email and password."""

    if not email or not password:
        return None

    normalized_email = email.strip().lower()

    with get_db_session() as db:
        user = db.scalar(
            select(User)
            .options(joinedload(User.apartment))
            .where(User.email == normalized_email)
        )

        if user is None:
            return None

        if not user.is_active:
            return None

        if not verify_password(
            password,
            user.password_hash,
        ):
            return None

        user.last_login_at = datetime.now(timezone.utc).replace(
            tzinfo=None
        )

        db.add(user)

        return user
