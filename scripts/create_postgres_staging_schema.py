
"""Initialize an EMPTY Neon PostgreSQL staging database.

Blue Moon Apartments — Sprint 12C.4

Usage:
    python -m scripts.create_postgres_staging_schema
    python -m scripts.create_postgres_staging_schema --create

Safety:
- Requires a direct Neon PostgreSQL connection.
- Requires an SSL-enabled connection.
- Requires SCRAM channel binding.
- Rejects an existing nonempty public schema.
- Requires explicit confirmation before creation.
- Creates application tables in one transaction.
- Does not seed users or real data.
- Does not access the local SQLite database.
- Does not drop or overwrite existing tables.
- Does not print database passwords or connection URLs.
"""

import argparse
from getpass import getpass

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

from database.models import Base


# ==========================================================
# CONFIGURATION
# ==========================================================

SUPPORTED_DRIVERS = (
    "postgres",
    "postgresql",
    "postgresql+psycopg",
)

ALLOWED_SSL_MODES = (
    "require",
    "verify-ca",
    "verify-full",
)

# Stable advisory lock used only during schema creation.
SCHEMA_CREATION_LOCK_KEY = 4777571570633994241


# ==========================================================
# CONNECTION URL VALIDATION
# ==========================================================

def read_staging_url():
    """Read and validate a direct Neon connection URL."""

    raw_url = getpass(
        "Paste DIRECT Neon staging URL (hidden): "
    ).strip()

    if not raw_url:
        raise ValueError(
            "The PostgreSQL connection URL is required."
        )

    try:
        url = make_url(raw_url)

    except Exception:
        raise ValueError(
            "Invalid PostgreSQL connection URL."
        ) from None

    # ------------------------------------------------------
    # VERIFY DATABASE DRIVER
    # ------------------------------------------------------

    if url.drivername not in SUPPORTED_DRIVERS:
        raise ValueError(
            "Only PostgreSQL connection URLs are supported."
        )

    # ------------------------------------------------------
    # VERIFY NEON HOSTNAME
    # ------------------------------------------------------

    hostname = (url.host or "").lower()

    if not hostname.endswith(".neon.tech"):
        raise ValueError(
            "Expected a Neon PostgreSQL hostname."
        )

    if "-pooler." in hostname:
        raise ValueError(
            "Use a DIRECT Neon connection URL, "
            "not a pooled connection."
        )

    # ------------------------------------------------------
    # VERIFY CONNECTION DETAILS
    # ------------------------------------------------------

    if (
        not url.username
        or not url.password
        or not url.database
    ):
        raise ValueError(
            "The PostgreSQL connection URL "
            "is missing required credentials."
        )

    # ------------------------------------------------------
    # REQUIRE ENCRYPTED CONNECTION
    # ------------------------------------------------------

    sslmode = url.query.get("sslmode")

    if sslmode not in ALLOWED_SSL_MODES:
        raise ValueError(
            "An SSL-enabled connection is required. "
            "Use sslmode=require or stronger."
        )

    # ------------------------------------------------------
    # USE PSYCOPG VERSION 3
    # ------------------------------------------------------

    url = url.set(
        drivername="postgresql+psycopg"
    )

    # Require PostgreSQL SCRAM channel binding.
    # Do not remove the existing sslmode parameter.

    url = url.update_query_dict(
        {
            "channel_binding": "require",
        }
    )

    return url


# ==========================================================
# PUBLIC SCHEMA INSPECTION
# ==========================================================

def inspect_public_schema(connection):
    """Inspect existing public schema objects.

    This function performs metadata queries only.
    It does not create or modify database objects.
    """

    inspector = inspect(connection)

    tables = inspector.get_table_names(
        schema="public"
    )

    views = inspector.get_view_names(
        schema="public"
    )

    materialized_views = (
        inspector.get_materialized_view_names(
            schema="public"
        )
    )

    sequences = inspector.get_sequence_names(
        schema="public"
    )

    return {
        "tables": tables,
        "views": views,
        "materialized_views": materialized_views,
        "sequences": sequences,
    }


def schema_is_empty(objects):
    """Check whether the inspected schema is empty."""

    return all(
        len(names) == 0
        for names in objects.values()
    )


def display_schema_objects(objects):
    """Display schema object counts without exposing data."""

    print("\nExisting public schema objects:")

    for category, names in objects.items():
        print(
            f"  {category}: {len(names)}"
        )


# ==========================================================
# DATABASE CONNECTION
# ==========================================================

def create_staging_engine(url):
    """Create an isolated PostgreSQL SQLAlchemy engine."""

    return create_engine(
        url,
        poolclass=NullPool,
        pool_pre_ping=True,
        hide_parameters=True,
        echo=False,
        connect_args={
            "connect_timeout": 15,
        },
    )


# ==========================================================
# READ-ONLY STAGING DATABASE PREVIEW
# ==========================================================

def preview_staging_database(engine, url):
    """Validate the target database and inspect its schema."""

    with engine.connect() as connection:

        database_name = connection.scalar(
            text(
                "SELECT current_database()"
            )
        )

        current_role = connection.scalar(
            text(
                "SELECT current_user"
            )
        )

        # Important:
        #
        # Neon uses a PostgreSQL connection proxy.
        # pg_stat_ssl reports backend-side connection
        # information and is not a reliable way to
        # verify client-to-Neon TLS.
        #
        # TLS requirements are enforced through
        # sslmode in the connection configuration.
        #
        # Channel binding is also explicitly required.
        #
        # A successful connection demonstrates that
        # those requested transport requirements
        # were accepted by the PostgreSQL client.

        objects = inspect_public_schema(
            connection
        )

    expected_tables = {
        table.name
        for table in Base.metadata.tables.values()
    }

    if not expected_tables:
        raise RuntimeError(
            "No application tables were registered "
            "in SQLAlchemy metadata."
        )

    if database_name != url.database:
        raise RuntimeError(
            "Connected database does not match "
            "the requested database."
        )

    print("\nDatabase:", database_name)
    print("Database role:", current_role)

    print(
        "Configured SSL mode:",
        url.query.get("sslmode"),
    )

    print(
        "Channel binding:",
        url.query.get("channel_binding"),
    )

    print(
        "Expected application tables:",
        len(expected_tables),
    )

    display_schema_objects(
        objects
    )

    return (
        database_name,
        expected_tables,
        objects,
    )


# ==========================================================
# CREATE POSTGRESQL APPLICATION SCHEMA
# ==========================================================

def create_staging_schema(
    engine,
    expected_tables,
):
    """Create all application tables transactionally.

    Refuses creation if the public schema already
    contains inspected database objects.

    A transaction-scoped advisory lock prevents
    concurrent runs of this same initialization
    script from creating tables simultaneously.
    """

    with engine.begin() as connection:

        # --------------------------------------------------
        # ACQUIRE INITIALIZATION LOCK
        # --------------------------------------------------

        connection.execute(
            text(
                "SELECT pg_advisory_xact_lock(:lock_key)"
            ),
            {
                "lock_key": SCHEMA_CREATION_LOCK_KEY,
            },
        )

        # --------------------------------------------------
        # USE PUBLIC SCHEMA
        # --------------------------------------------------

        connection.exec_driver_sql(
            "SET LOCAL search_path TO public"
        )

        # --------------------------------------------------
        # CHECK SCHEMA AGAIN BEFORE WRITING
        # --------------------------------------------------

        current_objects = inspect_public_schema(
            connection
        )

        if not schema_is_empty(
            current_objects
        ):
            raise RuntimeError(
                "The public schema is no longer empty. "
                "Creation has been cancelled."
            )

        # --------------------------------------------------
        # CREATE SQLALCHEMY TABLES AND INDEXES
        # --------------------------------------------------

        Base.metadata.create_all(
            bind=connection,
            checkfirst=False,
        )

        # --------------------------------------------------
        # VERIFY TABLE CREATION BEFORE COMMIT
        # --------------------------------------------------

        created_tables = set(
            inspect(connection).get_table_names(
                schema="public"
            )
        )

        if created_tables != expected_tables:

            missing_tables = (
                expected_tables - created_tables
            )

            unexpected_tables = (
                created_tables - expected_tables
            )

            print(
                "\nMissing application tables:",
                len(missing_tables),
            )

            print(
                "Unexpected application tables:",
                len(unexpected_tables),
            )

            raise RuntimeError(
                "Created PostgreSQL tables do not "
                "match SQLAlchemy metadata."
            )

    # Transaction committed successfully.
    # Verify that tables are visible to a new connection.

    with engine.connect() as connection:

        committed_tables = set(
            inspect(connection).get_table_names(
                schema="public"
            )
        )

    if committed_tables != expected_tables:
        raise RuntimeError(
            "PostgreSQL schema creation committed, "
            "but post-commit verification failed. "
            "Inspect staging before retrying."
        )

    return len(committed_tables)


# ==========================================================
# MAIN SCRIPT
# ==========================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Safely initialize an empty Neon "
            "PostgreSQL staging database."
        )
    )

    parser.add_argument(
        "--create",
        action="store_true",
        help=(
            "Create application tables after "
            "explicit confirmation."
        ),
    )

    args = parser.parse_args()

    print("=" * 55)
    print("BLUE MOON APARTMENTS")
    print("Neon PostgreSQL Staging Schema Setup")
    print("=" * 55)

    # ------------------------------------------------------
    # GET DATABASE CONNECTION URL
    # ------------------------------------------------------

    try:
        url = read_staging_url()

    except ValueError as exc:
        print(
            "\nConnection configuration error:",
            str(exc),
        )
        raise SystemExit(1) from None

    # ------------------------------------------------------
    # CREATE ISOLATED DATABASE ENGINE
    # ------------------------------------------------------

    engine = create_staging_engine(
        url
    )

    try:

        # --------------------------------------------------
        # PREVIEW DATABASE
        # --------------------------------------------------

        (
            database_name,
            expected_tables,
            objects,
        ) = preview_staging_database(
            engine,
            url,
        )

        # --------------------------------------------------
        # REJECT NONEMPTY SCHEMA
        # --------------------------------------------------

        if not schema_is_empty(objects):

            print(
                "\nSTOP: The public schema is not empty."
            )

            print(
                "Existing tables, views, materialized "
                "views, or sequences were detected."
            )

            print(
                "No database objects were changed."
            )

            return

        # --------------------------------------------------
        # PREVIEW MODE
        # --------------------------------------------------

        if not args.create:

            print("\nPreview successful.")

            print(
                "Public schema is empty."
            )

            print(
                "No tables were created."
            )

            print(
                "Local SQLite database: untouched."
            )

            print(
                "\nTo create the staging schema, run:"
            )

            print(
                "python -m "
                "scripts.create_postgres_staging_schema "
                "--create"
            )

            return

        # --------------------------------------------------
        # EXPLICIT USER CONFIRMATION
        # --------------------------------------------------

        confirmation_text = (
            f"CREATE-STAGING-{database_name}"
        )

        print("\nWARNING:")
        print(
            "You are about to create the application "
            "schema in the selected Neon database."
        )

        print(
            "This operation creates tables and indexes."
        )

        print(
            "It will not seed administrator accounts, "
            "resident records, or payment information."
        )

        confirmation = input(
            "\nType "
            + confirmation_text
            + " to continue: "
        ).strip()

        if confirmation != confirmation_text:

            print(
                "\nCancelled. No changes made."
            )

            return

        # --------------------------------------------------
        # CREATE DATABASE SCHEMA
        # --------------------------------------------------

        created_count = create_staging_schema(
            engine,
            expected_tables,
        )

        # --------------------------------------------------
        # SUCCESS OUTPUT
        # --------------------------------------------------

        print("\n" + "=" * 55)
        print("SUCCESS!")
        print("=" * 55)

        print(
            "PostgreSQL staging schema created."
        )

        print(
            "Tables verified:",
            created_count,
        )

        print(
            "Database:",
            database_name,
        )

        print(
            "Local SQLite database: untouched."
        )

        print(
            "Administrator accounts: not created."
        )

        print(
            "Resident demo records: not created."
        )

        print(
            "Real data migration: not performed."
        )

        print(
            "\nNext step: PostgreSQL integration "
            "and concurrency testing."
        )

    # ------------------------------------------------------
    # SAFE ERROR HANDLING
    # ------------------------------------------------------

    except RuntimeError as exc:

        print(
            "\nSafety or verification error:",
            str(exc),
        )

        print(
            "No local SQLite data was modified."
        )

        raise SystemExit(1) from None

    except SQLAlchemyError as exc:

        print(
            "\nPostgreSQL operation failed:",
            type(exc).__name__,
        )

        # Avoid printing raw database exceptions,
        # which can contain connection information.

        print(
            "Check Neon connectivity, database "
            "permissions, and schema compatibility."
        )

        print(
            "Do not retry creation without checking "
            "whether any tables already exist."
        )

        raise SystemExit(1) from None

    finally:

        engine.dispose()


if __name__ == "__main__":
    main()
