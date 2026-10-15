
"""Trusted CLI for initial Blue Moon Super Admin provisioning.

This script assigns the first Super Admin role to an existing,
active, unassigned administrator.

Never expose this CLI as a Streamlit action or web endpoint.
"""

import argparse
import getpass
import os
import re
import sys

from hmac import compare_digest
from pathlib import Path

from sqlalchemy import func, select

from core.config import IS_PRODUCTION
from core.security import verify_password
from database.db import engine, get_db_session
from database.models import (
    AdminEmployee,
    User,
)
from services.admin_rbac_service import (
    bootstrap_initial_super_admin,
)


LOCAL_BOOTSTRAP_FLAG = "BLUEMOON_ALLOW_ROLE_BOOTSTRAP"
LOCAL_BOOTSTRAP_VALUE = "ALLOW_ONE_TIME"

PRODUCTION_FLAG = (
    "BLUEMOON_ALLOW_PRODUCTION_BOOTSTRAP"
)
PRODUCTION_VALUE = "ALLOW_INITIAL_PROVISIONING"


# ==================================================
# CLI AUTHORIZATION
# ==================================================

def _require_trusted_terminal() -> None:
    """Require explicit authorization and an interactive shell."""

    if not sys.stdin.isatty():
        raise PermissionError(
            "Super Admin bootstrap requires "
            "an interactive trusted terminal."
        )

    if (
        os.getenv(LOCAL_BOOTSTRAP_FLAG)
        != LOCAL_BOOTSTRAP_VALUE
    ):
        raise PermissionError(
            "Super Admin bootstrap is disabled. "
            "Explicit one-time authorization is required."
        )

    if IS_PRODUCTION and (
        os.getenv(PRODUCTION_FLAG)
        != PRODUCTION_VALUE
    ):
        raise PermissionError(
            "Production bootstrap requires separate "
            "explicit provisioning authorization."
        )

    # Prevent creating a new SQLite database just because
    # the CLI was launched from an incorrect directory.
    if engine.dialect.name == "sqlite":

        filename = engine.url.database

        if (
            not filename
            or filename == ":memory:"
            or not Path(filename).is_file()
        ):
            raise RuntimeError(
                "Configured SQLite database does not exist. "
                "Verify the project directory and DATABASE_URL."
            )


# ==================================================
# VERIFY EXISTING ADMINISTRATOR IDENTITY
# ==================================================

def _verify_existing_admin(
    email: str,
    password: str,
) -> None:
    """Require knowledge of the target administrator password."""

    with get_db_session() as db:

        user = db.scalar(
            select(User).where(
                func.lower(User.email) == email
            )
        )

        if (
            user is None
            or str(user.role or "").lower() != "admin"
            or not user.is_active
        ):
            raise PermissionError(
                "Administrator verification failed."
            )

        employee = db.scalar(
            select(AdminEmployee).where(
                AdminEmployee.user_id == user.id,
                AdminEmployee.is_active.is_(True),
            )
        )

        if employee is None:
            raise PermissionError(
                "Administrator verification failed."
            )

        if not verify_password(
            password,
            user.password_hash,
        ):
            raise PermissionError(
                "Administrator verification failed."
            )


# ==================================================
# MAIN COMMAND
# ==================================================

def main() -> int:

    parser = argparse.ArgumentParser(
        description=(
            "One-time trusted Super Admin provisioning."
        )
    )

    parser.add_argument(
        "--email",
        required=True,
        help=(
            "Email of the existing initial administrator."
        ),
    )

    args = parser.parse_args()

    _require_trusted_terminal()

    email = args.email.strip().lower()

    if (
        len(email) > 255
        or not re.fullmatch(
            r"[^@\s]+@[^@\s]+\.[^@\s]+",
            email,
        )
    ):
        raise ValueError(
            "Provide a valid existing administrator email."
        )

    print()
    print("=" * 60)
    print("BLUE MOON — INITIAL SUPER ADMIN PROVISIONING")
    print("=" * 60)

    print(
        "Database:",
        engine.url.render_as_string(
            hide_password=True
        ),
    )

    print("Target:", email)

    print()
    print(
        "This operation grants full Super Admin privileges."
    )

    print(
        "It should only be used during initial "
        "system provisioning."
    )

    print()
    print(
        "Enter the existing administrator password "
        "to authorize provisioning."
    )

    password = getpass.getpass(
        "Administrator password: "
    )

    _verify_existing_admin(
        email,
        password,
    )

    password = None

    print()
    print(
        "Type the complete administrator email "
        "to confirm this privileged operation."
    )

    confirmation = input(
        "Confirmation: "
    ).strip().lower()

    if not compare_digest(
        confirmation,
        email,
    ):
        raise PermissionError(
            "Confirmation failed. No changes made."
        )

    # This backend function enforces the one-time
    # role assignment rules and records an audit event.
    user_id = bootstrap_initial_super_admin(
        email
    )

    print()
    print("=" * 60)
    print(
        "Super Admin role assigned successfully."
    )
    print("Administrator ID:", user_id)
    print()
    print(
        "Remove all temporary bootstrap authorization "
        "environment variables immediately."
    )
    print("=" * 60)

    return 0


if __name__ == "__main__":

    try:
        raise SystemExit(main())

    except (
        ValueError,
        PermissionError,
        RuntimeError,
    ) as exc:
        raise SystemExit(
            f"Bootstrap refused: {exc}"
        ) from exc
