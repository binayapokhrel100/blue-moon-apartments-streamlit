
"""Command-line security retention maintenance."""

import argparse

from services.security_retention_service import (
    DEFAULT_FAILURE_ATTEMPT_DAYS,
    DEFAULT_LOGIN_EVENT_DAYS,
    DEFAULT_BATCH_SIZE,
    cleanup_security_retention,
    preview_security_retention,
)


def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Preview or explicitly clean up expired "
            "Blue Moon authentication security records."
        )
    )

    parser.add_argument(
        "--login-days",
        type=int,
        default=DEFAULT_LOGIN_EVENT_DAYS,
    )

    parser.add_argument(
        "--attempt-days",
        type=int,
        default=DEFAULT_FAILURE_ATTEMPT_DAYS,
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Enable deletion.",
    )

    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Confirm the deletion operation.",
    )

    args = parser.parse_args()

    if args.apply != args.confirm:
        parser.error(
            "Deletion requires both --apply and --confirm."
        )

    try:
        preview = preview_security_retention(
            login_days=args.login_days,
            attempt_days=args.attempt_days,
        )

    except ValueError as exc:
        parser.error(str(exc))

    print()
    print("=" * 54)
    print("BLUE MOON — SECURITY RETENTION")
    print("=" * 54)

    print(
        "Login event cutoff (UTC):",
        preview["login_event_cutoff"],
    )

    print(
        "Failure attempt cutoff (UTC):",
        preview["failure_attempt_cutoff"],
    )

    print(
        "Eligible login events:",
        preview["eligible_login_events"],
    )

    print(
        "Eligible failed attempts:",
        preview["eligible_failure_attempts"],
    )

    if not args.apply:

        print()
        print("DRY RUN — no records were deleted.")
        return

    # Both --apply and --confirm are required.

    result = cleanup_security_retention(
        confirm=True,
        login_days=args.login_days,
        attempt_days=args.attempt_days,
        batch_size=args.batch_size,
    )

    print()
    print("CLEANUP COMPLETED")

    print(
        "Deleted login events:",
        result["deleted_login_events"],
    )

    print(
        "Deleted failure attempts:",
        result["deleted_failure_attempts"],
    )

    print(
        "Remaining eligible login events:",
        result["remaining_eligible_login_events"],
    )

    print(
        "Remaining eligible failed attempts:",
        result["remaining_eligible_failure_attempts"],
    )


if __name__ == "__main__":
    main()
