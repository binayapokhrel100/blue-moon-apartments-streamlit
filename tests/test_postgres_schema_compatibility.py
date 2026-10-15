
"""Cross-database schema compatibility tests.

Blue Moon Apartments — Sprint 12C
Verify that important database constraints behave
consistently on SQLite and PostgreSQL.
"""

from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.schema import CreateIndex

from database.models import MoveOutInspection


INDEX_NAME = "uq_open_moveout_inspection_per_apartment"


def test_moveout_unique_index_is_partial_on_both_databases():
    """Verify the partial unique index on both databases.

    Only one unfinished move-out inspection is allowed
    per apartment.

    Completed inspections must remain available
    as historical records.
    """

    # Use the actual SQLAlchemy model table.
    # Do not assume the underlying database table name.
    table = MoveOutInspection.__table__

    matching_indexes = [
        index
        for index in table.indexes
        if index.name == INDEX_NAME
    ]

    assert len(matching_indexes) == 1, (
        f"Expected exactly one index named {INDEX_NAME}"
    )

    index = matching_indexes[0]

    # The constraint must enforce uniqueness.
    assert index.unique is True

    # Verify generated DDL for both database engines.
    for dialect in (
        sqlite.dialect(),
        postgresql.dialect(),
    ):
        ddl = str(
            CreateIndex(index).compile(
                dialect=dialect
            )
        )

        normalized_ddl = ddl.upper()

        assert "UNIQUE INDEX" in normalized_ddl, ddl

        # A partial unique index must include WHERE.
        assert " WHERE " in normalized_ddl, ddl

        # Restrict uniqueness to unfinished inspections.
        assert "status" in ddl.lower(), ddl
        assert "'pending'" in ddl.lower(), ddl
        assert "'inspected'" in ddl.lower(), ddl

def test_all_application_tables_compile_for_postgresql():
    """Compile every SQLAlchemy table and index for PostgreSQL.

    This test does not connect to a database or
    create, modify, or delete any records.
    """

    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateTable, CreateIndex

    from database.models import Base

    dialect = postgresql.dialect()

    tables = sorted(
        Base.metadata.tables.values(),
        key=lambda table: table.name,
    )

    assert tables, "No database tables were registered."

    for table in tables:

        # Validate CREATE TABLE SQL.
        try:
            table_ddl = str(
                CreateTable(table).compile(
                    dialect=dialect
                )
            )
        except Exception as exc:
            raise AssertionError(
                f"PostgreSQL table compilation failed: "
                f"{table.name}"
            ) from exc

        assert "CREATE TABLE" in table_ddl.upper()

        # Validate every declared index.
        for index in table.indexes:

            try:
                index_ddl = str(
                    CreateIndex(index).compile(
                        dialect=dialect
                    )
                )
            except Exception as exc:
                raise AssertionError(
                    f"PostgreSQL index compilation failed: "
                    f"{index.name} on {table.name}"
                ) from exc

            assert "CREATE" in index_ddl.upper()
            assert "INDEX" in index_ddl.upper()
