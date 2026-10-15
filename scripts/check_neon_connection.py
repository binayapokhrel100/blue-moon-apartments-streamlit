
"""Read-only Neon PostgreSQL connectivity check.

Blue Moon Apartments — Sprint 12C

This script:
- Does not access the local SQLite database
- Does not create or modify PostgreSQL tables
- Does not save database credentials
- Uses a direct, encrypted PostgreSQL connection
"""

from getpass import getpass

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool
from sqlalchemy.exc import SQLAlchemyError


def main():
    print("=" * 55)
    print("BLUE MOON APARTMENTS")
    print("PostgreSQL Staging Connection Check")
    print("=" * 55)

    print(
        "\nPaste the DIRECT Neon connection URL "
        "when prompted."
    )
    print("Your input will be hidden.\n")

    raw_url = getpass(
        "Neon connection URL: "
    ).strip()

    if not raw_url:
        raise ValueError(
            "Connection URL cannot be empty."
        )

    url = make_url(raw_url)

    if url.drivername not in (
        "postgresql",
        "postgres",
        "postgresql+psycopg",
    ):
        raise ValueError(
            "Expected a PostgreSQL connection URL."
        )

    # Force the SQLAlchemy psycopg v3 driver.
    url = url.set(
        drivername="postgresql+psycopg"
    )

    hostname = (url.host or "").lower()

    if not hostname.endswith(".neon.tech"):
        raise ValueError(
            "Expected a Neon database hostname."
        )

    if "-pooler." in hostname:
        raise ValueError(
            "Use the Direct connection URL "
            "for this initial staging check."
        )

    sslmode = url.query.get("sslmode")

    if sslmode not in (
        "require",
        "verify-ca",
        "verify-full",
    ):
        raise ValueError(
            "An SSL-enabled PostgreSQL "
            "connection is required."
        )

    engine = create_engine(
        url,
        poolclass=NullPool,
        connect_args={
            "connect_timeout": 15
        },
        pool_pre_ping=True,
        hide_parameters=True,
        echo=False,
    )

    try:
        with engine.connect() as connection:

            info = connection.execute(
                text(
                    "SELECT current_database() "
                    "AS database_name, "
                    "current_user AS role_name"
                )
            ).mappings().one()

            table_count = connection.scalar(
                text(
                    "SELECT COUNT(*) "
                    "FROM information_schema.tables "
                    "WHERE table_schema = 'public' "
                    "AND table_type = 'BASE TABLE'"
                )
            )

            print("\nConnection successful!")
            print("Database:", info["database_name"])
            print("PostgreSQL connection: OK")
            print("Public tables:", table_count)
            print("SSL mode:", sslmode)
            print("\nRead-only checks completed.")

    except SQLAlchemyError as exc:
        print(
            "\nPostgreSQL connection failed:",
            type(exc).__name__,
        )
        raise SystemExit(1) from None

    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
