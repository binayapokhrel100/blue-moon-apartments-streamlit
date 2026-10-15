
"""One-time production administrator provisioning.

Creates the initial administrator without granting an RBAC role.
Run the existing bootstrap_super_admin.py separately afterward.

Never expose this script through Streamlit or an API.
"""

import getpass
import re
import sys
from hmac import compare_digest

from sqlalchemy import func, select

from core.config import IS_PRODUCTION
from core.security import hash_password
from database.db import engine, get_db_session, init_db
from database.models import (
    User,
    AdminEmployee,
    AdminCredentialState,
    AdminRoleAssignment,
    AdminRoleChangeEvent,
)
from services.auth_throttle_service import (
    acquire_authentication_lock,
)


def main():
    if not IS_PRODUCTION:
        raise PermissionError("Production mode required.")

    if engine.dialect.name != "postgresql":
        raise PermissionError("PostgreSQL required.")

    if not sys.stdin.isatty():
        raise PermissionError("Interactive terminal required.")

    print("\nBLUE MOON - FIRST PRODUCTION ADMIN")
    print("Database:", engine.url.database)
    print("Host:", engine.url.host)

    init_db()

    email = input("Administrator email: ").strip().lower()
    employee_id = input("Employee ID (BM-EMP-0001): ").strip().upper()

    if (
        len(email) > 255
        or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)
    ):
        raise ValueError("Invalid administrator email.")

    if not re.fullmatch(r"BM-EMP-[A-Z0-9]{4,12}", employee_id):
        raise ValueError("Invalid employee ID.")

    password = getpass.getpass("Initial password: ")
    confirmation_password = getpass.getpass("Confirm password: ")

    if not compare_digest(password, confirmation_password):
        raise ValueError("Passwords do not match.")

    password_bytes = password.encode("utf-8")

    if not 12 <= len(password_bytes) <= 72:
        raise ValueError("Password must be 12-72 UTF-8 bytes.")

    if not all([
        any(c.isupper() for c in password),
        any(c.islower() for c in password),
        any(c.isdigit() for c in password),
        any(not c.isalnum() for c in password),
    ]):
        raise ValueError(
            "Password requires uppercase, lowercase, "
            "number, and special character."
        )

    password_hash = hash_password(password)
    password = None
    confirmation_password = None

    print("\nTarget administrator:", email)
    print("Employee ID:", employee_id)
    print("Database:", engine.url.database)
    print("Host:", engine.url.host)

    confirmation = input(
        "\nType 'CREATE FIRST ADMIN' to proceed: "
    ).strip()

    if confirmation != "CREATE FIRST ADMIN":
        raise PermissionError("Provisioning cancelled.")

    with get_db_session() as db:
        acquire_authentication_lock(db)

        # This is a fresh-install-only operation.
        checks = (
            (User, "users"),
            (AdminEmployee, "admin employees"),
            (AdminRoleAssignment, "role assignments"),
            (AdminRoleChangeEvent, "role audit events"),
        )

        for model, name in checks:
            count = db.scalar(select(func.count()).select_from(model))
            if count:
                raise PermissionError(
                    f"Provisioning refused: existing {name}."
                )

        credential_count = db.scalar(
            select(func.count()).select_from(
                AdminCredentialState
            )
        )
        if credential_count:
            raise PermissionError(
                "Provisioning refused: existing credential states."
            )

        account = User(
            first_name="Blue Moon",
            last_name="Administrator",
            email=email,
            password_hash=password_hash,
            role="admin",
            is_active=True,
            apartment_id=None,
        )

        db.add(account)
        db.flush()

        db.add(
            AdminEmployee(
                user_id=account.id,
                employee_id=employee_id,
                is_active=True,
            )
        )

        db.add(
            AdminCredentialState(
                user_id=account.id,
                must_change_password=True,
                credential_version=0,
            )
        )

        db.flush()
        user_id = account.id

    print("\nAdministrator created successfully.")
    print("User ID:", user_id)
    print("RBAC role: Not yet assigned")
    print("First-login password change: Required")
    print("Next: Run trusted Super Admin bootstrap.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, PermissionError, RuntimeError) as exc:
        raise SystemExit(f"Provisioning refused: {exc}") from exc
