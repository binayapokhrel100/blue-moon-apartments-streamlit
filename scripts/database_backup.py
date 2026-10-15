
"""Blue Moon Apartments SQLite backup CLI.

Default operation: read-only preview.

No command restores data over the application's
configured database.
"""

import argparse
import sys

from pathlib import Path

from services.database_backup_service import (
    configured_database_path,
    create_verified_backup,
    verify_disposable_restore,
    verify_sqlite_file,
)


# ==========================================================
# COMMAND-LINE ENTRY POINT
# ==========================================================

def main() -> int:

    parser = argparse.ArgumentParser(
        description=(
            "Preview, create, and verify "
            "safe SQLite database backups."
        )
    )

    actions = parser.add_mutually_exclusive_group()

    actions.add_argument(
        "--backup",
        action="store_true",
        help="Create a new verified backup.",
    )

    actions.add_argument(
        "--verify",
        metavar="BACKUP_FILE",
        help=(
            "Test restoration of an existing backup "
            "without modifying the application database."
        ),
    )

    parser.add_argument(
        "--output-dir",
        default=str(
            Path.home() / "BlueMoonSecureBackups"
        ),
        help=(
            "Backup destination outside the project. "
            "Default: ~/BlueMoonSecureBackups"
        ),
    )

    args = parser.parse_args()

    try:

        # ==========================================
        # VERIFY EXISTING BACKUP
        # ==========================================

        if args.verify:

            result = verify_disposable_restore(
                args.verify
            )

            print(
                "Backup restore verification: PASSED"
            )

            print(
                "Tables verified:",
                result["table_count"],
            )

            return 0

        # ==========================================
        # IDENTIFY CONFIGURED DATABASE
        # ==========================================

        source = configured_database_path()

        # ==========================================
        # CREATE BACKUP
        # ==========================================

        if args.backup:

            result = create_verified_backup(
                source,
                backup_directory=args.output_dir,
            )

            print(
                "Verified backup created:",
                result["path"],
            )

            print(
                "Backup size (bytes):",
                result["bytes"],
            )

            print(
                "Tables verified:",
                result["table_count"],
            )

            print(
                "Contains sensitive data: store on "
                "encrypted, access-restricted storage."
            )

            return 0

        # ==========================================
        # DEFAULT — READ-ONLY PREVIEW
        # ==========================================

        info = verify_sqlite_file(
            source
        )

        print(
            "Configured database:",
            source,
        )

        print(
            "SQLite integrity: OK"
        )

        print(
            "Application tables:",
            info["table_count"],
        )

        print(
            "Planned backup directory:",
            Path(args.output_dir).expanduser(),
        )

        print(
            "Preview only: no backup created "
            "and no data changed."
        )

        return 0

    except (
        OSError,
        ValueError,
        RuntimeError,
    ) as exc:

        print(
            "Backup operation stopped:",
            exc,
            file=sys.stderr,
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(main())
