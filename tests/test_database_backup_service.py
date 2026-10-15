
"""Tests for Blue Moon Apartments SQLite backup service."""

import sqlite3

from pathlib import Path

import pytest

from services.database_backup_service import (
    create_verified_backup,
    verify_disposable_restore,
    verify_sqlite_file,
)


# ==========================================================
# TEMPORARY SQLITE DATABASE
# ==========================================================

@pytest.fixture
def sample(tmp_path):

    db = tmp_path / "live.db"

    with sqlite3.connect(db) as connection:

        connection.execute(
            "CREATE TABLE users "
            "(id INTEGER PRIMARY KEY, email TEXT)"
        )

        connection.execute(
            'CREATE TABLE "special""table" (name TEXT)'
        )

        connection.execute(
            "INSERT INTO users(email) VALUES (?)",
            ("person@example.test",),
        )

    return db


# ==========================================================
# TEST 1 — BACKUP VALID AND RESTORABLE
# ==========================================================

def test_backups_valid_and_isolated(
    sample,
    tmp_path,
):

    directory = (
        tmp_path / "backups"
    )

    result = create_verified_backup(
        sample,
        backup_directory=directory,
    )

    assert result["verified"] is True
    assert result["table_count"] == 2

    destination = Path(
        result["path"]
    )

    assert destination.exists()
    assert destination != sample

    with sqlite3.connect(
        destination
    ) as connection:

        value = connection.execute(
            "SELECT email FROM users"
        ).fetchone()[0]

        assert value == "person@example.test"


# ==========================================================
# TEST 2 — UNIQUE BACKUP FILENAMES
# ==========================================================

def test_multiple_backups_dont_overwrite(
    sample,
    tmp_path,
):

    directory = (
        tmp_path / "backups"
    )

    first = create_verified_backup(
        sample,
        backup_directory=directory,
    )

    second = create_verified_backup(
        sample,
        backup_directory=directory,
    )

    assert first["path"] != second["path"]


# ==========================================================
# TEST 3 — ORIGINAL DATABASE NOT MODIFIED
# ==========================================================

def test_read_only(sample):

    original_mtime = (
        sample.stat().st_mtime_ns
    )

    verify_sqlite_file(
        sample
    )

    verify_disposable_restore(
        sample
    )

    assert (
        sample.stat().st_mtime_ns
        == original_mtime
    )


# ==========================================================
# TEST 4 — MISSING DATABASE NOT CREATED
# ==========================================================

def test_missing_source_is_not_created(
    tmp_path,
):

    missing = (
        tmp_path / "missing.db"
    )

    with pytest.raises(FileNotFoundError):

        create_verified_backup(
            missing,
            backup_directory=(
                tmp_path / "backups"
            ),
        )

    assert not missing.exists()


# ==========================================================
# TEST 5 — INVALID DATABASE REJECTED
# ==========================================================

def test_not_sqlite_rejected(
    tmp_path,
):

    bad = (
        tmp_path / "bad.db"
    )

    bad.write_text(
        "not a database"
    )

    with pytest.raises(
        ValueError,
        match="not a supported SQLite",
    ):

        create_verified_backup(
            bad,
            backup_directory=(
                tmp_path / "backups"
            ),
        )


# ==========================================================
# TEST 6 — CORRUPTED BACKUP REJECTED
# ==========================================================

def test_corrupt_backup_is_detected(
    sample,
    tmp_path,
):

    result = create_verified_backup(
        sample,
        backup_directory=(
            tmp_path / "backups"
        ),
    )

    backup = Path(
        result["path"]
    )

    with backup.open(
        "r+b"
    ) as stream:

        stream.seek(0)
        stream.write(
            b"CORRUPTED!"
        )

    with pytest.raises(ValueError):

        verify_disposable_restore(
            backup
        )


# ==========================================================
# TEST 7 — WAL CHANGES INCLUDED
# ==========================================================

def test_wal_committed_changes_are_in_backup(
    sample,
    tmp_path,
):

    with sqlite3.connect(
        sample
    ) as connection:

        connection.execute(
            "PRAGMA journal_mode=WAL"
        )

        connection.execute(
            "INSERT INTO users(email) VALUES (?)",
            ("wal@example.test",),
        )

    result = create_verified_backup(
        sample,
        backup_directory=(
            tmp_path / "backups"
        ),
    )

    backup = Path(
        result["path"]
    )

    with sqlite3.connect(
        backup
    ) as connection:

        count = connection.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0]

        assert count == 2
