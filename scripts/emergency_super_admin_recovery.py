
"""Trusted local CLI for emergency Super Admin password recovery.

Examples:
    python -m scripts.emergency_super_admin_recovery
    python -m scripts.emergency_super_admin_recovery --generate-key
    python -m scripts.emergency_super_admin_recovery --issue-code

No Streamlit page or HTTP endpoint should invoke this tool.
"""

import argparse
import getpass
import secrets
import sys

from hashlib import sha256

from services.emergency_super_admin_service import (
    issue_emergency_super_admin_reset,
    preview_emergency_super_admin_recovery,
)


CONFIRMATION_TEXT = "ISSUE-EMERGENCY-RESET"


def _generate_key() -> None:
    """Generate a high-entropy key for offline provisioning."""

    key = secrets.token_urlsafe(48)

    verifier = sha256(
        key.encode("utf-8")
    ).hexdigest()

    print()
    print("=" * 66)
    print("BLUE MOON — EMERGENCY RECOVERY KEY PROVISIONING")
    print("=" * 66)

    print()
    print("EMERGENCY KEY (STORE OFFLINE):")
    print(key)

    print()
    print("ENVIRONMENT VARIABLE:")
    print("BM_EMERGENCY_RECOVERY_KEY_SHA256")

    print()
    print("CONFIGURED HASH VALUE:")
    print(verifier)

    print()
    print(
        "Keep the emergency key in a protected offline "
        "password vault."
    )
    print(
        "Only the HASH belongs in the environment variable."
    )
    print(
        "Never commit the raw key, print it in application "
        "logs, or share it in ordinary email."
    )

    print("=" * 66)


def _show_preview() -> dict:
    """Display current recovery eligibility without changes."""

    status = preview_emergency_super_admin_recovery()

    print()
    print("=" * 66)
    print("BLUE MOON — EMERGENCY RECOVERY PREVIEW")
    print("=" * 66)

    print(
        "Active Super Admin count:",
        status["active_super_admin_count"],
    )

    if status["eligible"]:
        print(
            "Eligible Super Admin:",
            status["email"],
        )

        print(
            "Employee ID:",
            status["employee_id"],
        )

        print("Emergency recovery eligible: YES")

    else:
        print("Emergency recovery eligible: NO")

        print(
            "Exactly one active Super Admin is required."
        )

    print("=" * 66)

    return status


def _issue_code() -> None:
    """Require interactive authorization and explicit confirmation."""

    if not sys.stdin.isatty():
        raise RuntimeError(
            "Emergency recovery requires an "
            "interactive, trusted terminal."
        )

    status = _show_preview()

    if not status["eligible"]:
        raise PermissionError(
            "This recovery procedure is not available "
            "for the current account configuration."
        )

    print()
    print("WARNING: EMERGENCY OPERATION")
    print(
        "This operation revokes current credential sessions "
        "and creates a short-lived password-reset code."
    )

    print()
    print(
        "Confirm the emergency has been authorized "
        "by the property system owner."
    )

    # ----------------------------------------------
    # COLLECT TARGET AND INCIDENT INFORMATION
    # ----------------------------------------------

    email = input(
        "\nSuper Admin email: "
    ).strip()

    employee_id = input(
        "Super Admin employee ID: "
    ).strip()

    operator_label = getpass.getuser()

    print(
        f"\nLocal OS operator label: {operator_label}"
    )

    ticket_reference = input(
        "Approved incident/ticket reference: "
    ).strip()

    reason = input(
        "Reason for emergency recovery: "
    ).strip()

    # ----------------------------------------------
    # REQUIRE EXPLICIT ACTION CONFIRMATION
    # ----------------------------------------------

    print()
    print(
        "To proceed, type exactly:",
        CONFIRMATION_TEXT,
    )

    confirmation = input("> ").strip()

    if confirmation != CONFIRMATION_TEXT:
        raise RuntimeError(
            "Emergency recovery cancelled."
        )

    # ----------------------------------------------
    # PROMPT FOR SECRET WITHOUT ECHOING
    # ----------------------------------------------

    recovery_key = getpass.getpass(
        "Offline emergency recovery key: "
    )

    # ----------------------------------------------
    # EXECUTE SECURE BACKEND OPERATION
    # ----------------------------------------------

    result = issue_emergency_super_admin_reset(
        email=email,
        employee_id=employee_id,
        recovery_key=recovery_key,
        operator_label=operator_label,
        ticket_reference=ticket_reference,
        reason=reason,
    )

    # Never print or save the original recovery key.
    recovery_key = None

    print()
    print("=" * 66)
    print("EMERGENCY RESET CODE ISSUED")
    print("=" * 66)

    print("Administrator:", result["email"])

    print()
    print("ONE-TIME RESET CODE:")
    print(result["reset_code"])

    print()
    print(
        "Expires at (UTC):",
        result["expires_at"].strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
    )

    print()
    print(
        "Redeem this code immediately through the existing "
        "Administrator Password Reset screen."
    )

    print(
        "The emergency key is now consumed. "
        "Provision and securely store a new key "
        "before the next emergency."
    )

    print(
        "Clear the terminal display and close the "
        "session after completing recovery."
    )

    print("=" * 66)


def main() -> int:

    parser = argparse.ArgumentParser(
        description=(
            "Offline emergency recovery for the "
            "sole active Blue Moon Super Admin."
        )
    )

    actions = parser.add_mutually_exclusive_group()

    actions.add_argument(
        "--generate-key",
        action="store_true",
        help="Generate a new offline recovery key and verifier.",
    )

    actions.add_argument(
        "--issue-code",
        action="store_true",
        help="Issue an emergency reset code with authorization.",
    )

    args = parser.parse_args()

    try:

        if args.generate_key:
            _generate_key()

        elif args.issue_code:
            _issue_code()

        else:
            _show_preview()

    except (
        PermissionError,
        ValueError,
        RuntimeError,
    ) as exc:

        print(
            f"\nRecovery operation refused: {exc}",
            file=sys.stderr,
        )

        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
