
"""One-time local development administrator seeding.

Not intended for production deployment.

The script creates an initial, unassigned administrator.
It never grants Super Admin privileges.
"""

import os
import re
import sys

from hmac import compare_digest

from dotenv import load_dotenv
from sqlalchemy import func, select

from core.config import APP_ENV
from core.security import hash_password, verify_password
from database.db import engine, get_db_session, init_db
from database.models import (
    AdminCredentialState,
    AdminEmployee,
    User,
)


SEED_PERMISSION_VARIABLE = "BLUEMOON_ALLOW_ADMIN_SEED"
SEED_PERMISSION_VALUE = "ALLOW_LOCAL_SEED"


# ==================================================
# LOCAL DEVELOPMENT AUTHORIZATION
# ==================================================

def _require_local_seed_authorization() -> None:
    """Fail closed outside an explicitly authorized local setup."""

    if APP_ENV != "development":
        raise PermissionError(
            "Administrator seeding is permitted only "
            "in the development environment."
        )

    if os.getenv(SEED_PERMISSION_VARIABLE) != SEED_PERMISSION_VALUE:
        raise PermissionError(
            "Administrator seeding is disabled. "
            "Explicit local seed authorization is required."
        )

    if not sys.stdin.isatty():
        raise PermissionError(
            "Administrator seeding requires "
            "an interactive local terminal."
        )


# ==================================================
# INPUT VALIDATION
# ==================================================

def _read_seed_settings() -> tuple[str, str, str]:
    """Read and validate the account being provisioned."""

    email = (
        os.getenv("BM_ADMIN_EMAIL") or ""
    ).strip().lower()

    employee_id = (
        os.getenv("BM_ADMIN_EMPLOYEE_ID") or ""
    ).strip().upper()

    password = os.getenv("BM_ADMIN_PASSWORD") or ""

    if not email or not employee_id or not password:
        raise ValueError(
            "Set BM_ADMIN_EMAIL, BM_ADMIN_EMPLOYEE_ID, "
            "and BM_ADMIN_PASSWORD before seeding."
        )

    if (
        len(email) > 255
        or not re.fullmatch(
            r"[^@\s]+@[^@\s]+\.[^@\s]+",
            email,
        )
    ):
        raise ValueError(
            "Provide a valid administrator email."
        )

    if not re.fullmatch(
        r"BM-EMP-[A-Z0-9]{4,12}",
        employee_id,
    ):
        raise ValueError(
            "Employee ID must look like BM-EMP-0001."
        )

    password_length = len(
        password.encode("utf-8")
    )

    if not 12 <= password_length <= 72:
        raise ValueError(
            "Password must contain 12 to 72 UTF-8 bytes."
        )

    if not (
        any(c.isupper() for c in password)
        and any(c.islower() for c in password)
        and any(c.isdigit() for c in password)
        and any(not c.isalnum() for c in password)
    ):
        raise ValueError(
            "Password must contain uppercase, lowercase, "
            "numeric, and special characters."
        )

    return email, employee_id, password


# ==================================================
# INITIAL ADMINISTRATOR SEED
# ==================================================

def seed_admin() -> None:
    """Create only the initial development administrator."""

    load_dotenv(override=False)

    # Authorization occurs before database initialization.
    _require_local_seed_authorization()

    email, employee_id, password = (
        _read_seed_settings()
    )

    print()
    print("BLUE MOON — LOCAL ADMINISTRATOR SEED")
    print(
        "Database:",
        engine.url.render_as_string(
            hide_password=True
        ),
    )
    print("Administrator:", email)
    print("Employee ID:", employee_id)
    print()
    print(
        "This operation must be performed only "
        "during initial development setup."
    )

    confirmation = input(
        "Type the administrator email to confirm: "
    ).strip().lower()

    if not compare_digest(
        confirmation,
        email,
    ):
        raise PermissionError(
            "Confirmation failed. Nothing changed."
        )

    # Creates missing tables, never drops existing ones.
    init_db()

    with get_db_session() as db:

        # ----------------------------------------------
        # DETECT EXISTING ADMINISTRATORS
        # ----------------------------------------------

        admin_count = int(
            db.scalar(
                select(func.count(User.id)).where(
                    func.lower(User.role) == "admin"
                )
            ) or 0
        )

        existing_user = db.scalar(
            select(User).where(
                func.lower(User.email) == email
            )
        )

        if existing_user is not None:

            # Idempotent reruns are permitted only for
            # the single previously created admin.
            if (
                str(existing_user.role or "").lower()
                != "admin"
            ):
                raise ValueError(
                    "The email belongs to a non-admin user."
                )

            if admin_count != 1:
                raise PermissionError(
                    "Initial administrator seeding is "
                    "disabled after additional "
                    "administrators have been created."
                )

            employee = db.scalar(
                select(AdminEmployee).where(
                    AdminEmployee.user_id
                    == existing_user.id
                )
            )

            if employee is None:
                raise ValueError(
                    "Administrator employee record missing."
                )

            if (
                not existing_user.is_active
                or not employee.is_active
            ):
                raise PermissionError(
                    "Existing administrator is inactive."
                )

            if not compare_digest(
                employee.employee_id.strip().upper(),
                employee_id,
            ):
                raise ValueError(
                    "Employee ID does not match."
                )

            if not verify_password(
                password,
                existing_user.password_hash,
            ):
                raise PermissionError(
                    "Existing administrator password "
                    "does not match."
                )

            result = (
                "Initial administrator already exists. "
                "No changes made."
            )

        else:

            # No new administrator can be seeded once
            # administrator provisioning has begun.
            if admin_count != 0:
                raise PermissionError(
                    "Administrator accounts already exist. "
                    "Use Super Admin Management instead."
                )

            duplicate_employee_id = db.scalar(
                select(AdminEmployee.id)
                .where(
                    func.upper(
                        AdminEmployee.employee_id
                    ) == employee_id
                )
                .limit(1)
            )

            if duplicate_employee_id is not None:
                raise ValueError(
                    "Employee ID is already assigned."
                )

            # ------------------------------------------
            # CREATE USER
            # ------------------------------------------

            account = User(
                first_name="Blue Moon",
                last_name="Administrator",
                email=email,
                password_hash=hash_password(password),
                role="admin",
                is_active=True,
                apartment_id=None,
            )

            db.add(account)
            db.flush()

            # ------------------------------------------
            # CREATE EMPLOYEE IDENTITY
            # ------------------------------------------

            db.add(
                AdminEmployee(
                    user_id=account.id,
                    employee_id=employee_id,
                    is_active=True,
                )
            )

            # ------------------------------------------
            # REQUIRE FIRST-LOGIN PASSWORD CHANGE
            # ------------------------------------------

            db.add(
                AdminCredentialState(
                    user_id=account.id,
                    must_change_password=True,
                    credential_version=0,
                )
            )

            # No RBAC role is assigned here.
            # Super Admin bootstrap remains separate.
            result = (
                "Initial development administrator created. "
                "First-login password change required."
            )

        db.flush()

    print()
    print("=" * 55)
    print(result)
    print("Administrator:", email)
    print("Employee ID:", employee_id)
    print("Password: not displayed")
    print("=" * 55)
    print()
    print(
        "Remove the seed password and temporary "
        "authorization from your environment after setup."
    )


# ==================================================
# COMMAND LINE ENTRY POINT
# ==================================================

if __name__ == "__main__":
    try:
        seed_admin()

    except (
        ValueError,
        PermissionError,
        RuntimeError,
    ) as exc:
        raise SystemExit(
            f"Administrator seed refused: {exc}"
        ) from exc
