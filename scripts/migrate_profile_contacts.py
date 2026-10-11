
"""Add optional contact columns to the SQLite resident profiles table."""

from database.db import engine, init_db


COLUMNS = {
    "secondary_email": "VARCHAR(255)",
    "secondary_phone": "VARCHAR(30)",
}


def migrate() -> None:

    if engine.dialect.name != "sqlite":
        raise RuntimeError(
            "This migration is for SQLite only."
        )

    # Creates the table if it does not exist.
    init_db()

    with engine.begin() as conn:

        existing = {
            row[1]
            for row in conn.exec_driver_sql(
                "PRAGMA table_info(resident_profiles)"
            ).all()
        }

        if not existing:
            raise RuntimeError(
                "resident_profiles table was not found."
            )

        for column, sql_type in COLUMNS.items():

            if column not in existing:

                conn.exec_driver_sql(
                    f"ALTER TABLE resident_profiles "
                    f"ADD COLUMN {column} {sql_type}"
                )

                print(f"Added column: {column}")

            else:

                print(f"Already present: {column}")

    print(
        "Resident profile contact migration complete."
    )


if __name__ == "__main__":
    migrate()
