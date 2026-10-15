
"""Verified, non-destructive SQLite backups for Blue Moon Apartments.

Never restore over the configured application database from this module.

Backups contain sensitive personal/account data.
Store them securely.
"""

from __future__ import annotations

import os
import secrets
import sqlite3
import tempfile

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


SQLITE_SIGNATURE = b"SQLite format 3\x00"


# ==========================================================
# VALIDATE SQLITE FILE
# ==========================================================

def _validated_sqlite_path(
    path: str | Path,
) -> Path:
    """Reject missing, non-file, or non-SQLite sources."""

    candidate = Path(path).expanduser().resolve(
        strict=True
    )

    if not candidate.is_file():
        raise ValueError(
            "SQLite database path is not a file."
        )

    with candidate.open("rb") as stream:

        if stream.read(
            len(SQLITE_SIGNATURE)
        ) != SQLITE_SIGNATURE:

            raise ValueError(
                "File is not a supported SQLite database."
            )

    return candidate


# ==========================================================
# RESOLVE APPLICATION DATABASE
# ==========================================================

def configured_database_path() -> Path:
    """
    Resolve the configured file-backed SQLite database.

    This does not create a new database.
    """

    from database.db import engine

    if engine.dialect.name != "sqlite":
        raise ValueError(
            "This backup tool supports SQLite databases only."
        )

    filename = engine.url.database

    if (
        not filename
        or filename == ":memory:"
        or filename.startswith("file:")
    ):
        raise ValueError(
            "A standard file-backed SQLite database is required."
        )

    return _validated_sqlite_path(filename)


# ==========================================================
# READ-ONLY SQLITE CONNECTION
# ==========================================================

def _read_connection(
    path: Path,
) -> sqlite3.Connection:
    """
    Open an existing database in read-only mode.

    A missing source database will not be created.
    """

    return sqlite3.connect(
        path.as_uri() + "?mode=ro",
        uri=True,
        timeout=30,
    )


# ==========================================================
# CHECK SQLITE DATABASE INTEGRITY
# ==========================================================

def verify_sqlite_file(
    path: str | Path,
) -> dict:
    """
    Verify SQLite database integrity.

    Returns table names and counts, never record contents.
    """

    source = _validated_sqlite_path(path)

    with closing(
        _read_connection(source)
    ) as connection:

        integrity = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()

        if (
            not integrity
            or integrity[0] != "ok"
        ):
            raise ValueError(
                "SQLite integrity check failed."
            )

        names = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' "
                "AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            )
        ]

    if not names:
        raise ValueError(
            "SQLite database has no application tables."
        )

    return {
        "table_count": len(names),
        "tables": names,
    }


# ==========================================================
# VERIFY RESTORATION TO TEMPORARY DATABASE
# ==========================================================

def verify_disposable_restore(
    backup_path: str | Path,
) -> dict:
    """
    Restore a backup into a temporary database.

    The temporary database is automatically deleted.

    The application's configured database is never
    overwritten or modified by this function.
    """

    backup = _validated_sqlite_path(
        backup_path
    )

    original = verify_sqlite_file(
        backup
    )

    with tempfile.TemporaryDirectory(
        prefix="blue_moon_restore_test_"
    ) as folder:

        disposable = (
            Path(folder) / "restored.sqlite3"
        )

        # ------------------------------------------
        # RESTORE INTO DISPOSABLE DATABASE
        # ------------------------------------------

        with closing(
            _read_connection(backup)
        ) as source, closing(
            sqlite3.connect(disposable)
        ) as destination:

            source.backup(
                destination,
                pages=100,
                sleep=0.1,
            )

        # ------------------------------------------
        # VERIFY RESTORED DATABASE INTEGRITY
        # ------------------------------------------

        restored = verify_sqlite_file(
            disposable
        )

        if restored["tables"] != original["tables"]:
            raise ValueError(
                "Restored database schema differs "
                "from backup."
            )

        # ------------------------------------------
        # COMPARE TABLE ROW COUNTS
        # ------------------------------------------

        with closing(
            _read_connection(backup)
        ) as before, closing(
            _read_connection(disposable)
        ) as after:

            for name in original["tables"]:

                quoted_name = (
                    '"'
                    + name.replace('"', '""')
                    + '"'
                )

                sql = (
                    f"SELECT COUNT(*) FROM {quoted_name}"
                )

                original_count = before.execute(
                    sql
                ).fetchone()[0]

                restored_count = after.execute(
                    sql
                ).fetchone()[0]

                if original_count != restored_count:
                    raise ValueError(
                        "Restored database row counts differ."
                    )

    return {
        "verified": True,
        "table_count": original["table_count"],
    }


# ==========================================================
# CREATE VERIFIED SQLITE BACKUP
# ==========================================================

def create_verified_backup(
    source_path: str | Path,
    *,
    backup_directory: str | Path,
) -> dict:
    """
    Create a unique, timestamped backup.

    Security safeguards:
    - Existing source must be a valid SQLite file.
    - Source is opened read-only.
    - Backup is created outside the project.
    - Unique name prevents routine overwrites.
    - Backup integrity is verified.
    - Restoration is tested in a temporary directory.
    - Failed or incomplete temporary backups are removed.
    """

    source = _validated_sqlite_path(
        source_path
    )

    folder = Path(
        backup_directory
    ).expanduser().resolve()

    project_root = (
        Path(__file__).resolve().parents[1]
    )

    # Do not save sensitive database backups inside
    # the source-code repository.

    if (
        folder == project_root
        or project_root in folder.parents
    ):
        raise ValueError(
            "Store backups outside the "
            "application/project folder."
        )

    folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not folder.is_dir():
        raise ValueError(
            "Backup destination is not a directory."
        )

    # ------------------------------------------
    # GENERATE UNIQUE BACKUP NAME
    # ------------------------------------------

    timestamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%SZ")

    filename = (
        f"blue_moon_{timestamp}_"
        f"{secrets.token_hex(5)}.sqlite3"
    )

    destination = folder / filename

    if (
        destination.exists()
        or destination.resolve() == source
    ):
        raise FileExistsError(
            "Backup destination already exists."
        )

    # ------------------------------------------
    # CREATE TEMPORARY BACKUP FILE
    # ------------------------------------------

    fd, temp_name = tempfile.mkstemp(
        prefix=".blue_moon_backup_",
        suffix=".tmp",
        dir=folder,
    )

    os.close(fd)

    staged = Path(temp_name)

    try:

        # ------------------------------------------
        # SQLITE ONLINE BACKUP
        # ------------------------------------------

        with closing(
            _read_connection(source)
        ) as original, closing(
            sqlite3.connect(staged)
        ) as output:

            original.backup(
                output,
                pages=100,
                sleep=0.1,
            )

        # ------------------------------------------
        # TEST RESTORE BEFORE KEEPING BACKUP
        # ------------------------------------------

        restore_result = (
            verify_disposable_restore(
                staged
            )
        )

        # ------------------------------------------
        # FINALIZE VERIFIED BACKUP
        # ------------------------------------------

        staged.rename(destination)

        return {
            "path": str(destination),
            "bytes": destination.stat().st_size,
            "verified": restore_result["verified"],
            "table_count": restore_result["table_count"],
        }

    finally:

        # Remove the incomplete staging file if an
        # exception occurs before finalization.

        staged.unlink(
            missing_ok=True
        )
