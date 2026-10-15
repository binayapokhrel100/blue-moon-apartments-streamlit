
"""Database connection and session management.

Blue Moon Apartments — Sprint 12C.10

Development:
    SQLite remains supported.
    Missing tables can be initialized locally.

Production:
    PostgreSQL is required.
    Certificate and hostname verification are required.
    Authentication channel binding is required.
    Existing schema is verified without creating tables.
"""

from contextlib import contextmanager
import certifi

from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from core.config import DATABASE_URL, IS_PRODUCTION
from database.models import Base


# ==========================================================
# DATABASE URL
# ==========================================================

database_url = make_url(DATABASE_URL)
database_backend = database_url.get_backend_name()


# ==========================================================
# PRODUCTION SECURITY VALIDATION
# ==========================================================

if IS_PRODUCTION:

    if database_backend != "postgresql":
        raise RuntimeError(
            "Production requires a persistent "
            "PostgreSQL database."
        )

    if database_url.query.get("sslmode") != "verify-full":
        raise RuntimeError(
            "Production PostgreSQL requires "
            "sslmode=verify-full."
        )

    if database_url.query.get(
        "channel_binding"
    ) != "require":
        raise RuntimeError(
            "Production PostgreSQL requires "
            "channel_binding=require."
        )


# ==========================================================
# DATABASE DRIVER
# ==========================================================

# Use psycopg version 3 consistently.
# Neon URLs commonly start with postgresql://.

if database_backend == "postgresql":
    database_url = database_url.set(
        drivername="postgresql+psycopg"
    )


# ==========================================================
# CONNECTION OPTIONS
# ==========================================================

connect_args = {}

if database_backend == "sqlite":

    connect_args = {
        "check_same_thread": False,
        "timeout": 30,
    }

elif database_backend == "postgresql":

    if IS_PRODUCTION:

        connect_args = {
            "sslmode": "verify-full",
            "sslrootcert": certifi.where(),
            "channel_binding": "require",
            "connect_timeout": 15,
        }

    else:

        connect_args = {
            "connect_timeout": 15,
        }
# ==========================================================
# SQLALCHEMY ENGINE
# ==========================================================

engine = create_engine(
    database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
    pool_recycle=300,
    hide_parameters=True,
    echo=False,
)


# ==========================================================
# SESSION FACTORY
# ==========================================================

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


# ==========================================================
# DATABASE INITIALIZATION
# ==========================================================

def init_db() -> None:
    """Initialize local SQLite or verify production schema.

    Development:
        Preserve existing create_all behavior.

    Production:
        Never create or drop tables automatically.
        Verify all required application tables exist.
    """

    if not IS_PRODUCTION:

        Base.metadata.create_all(
            bind=engine
        )

        return

    # Production tables must be provisioned separately
    # through approved schema setup or migrations.

    expected_tables = set(
        Base.metadata.tables.keys()
    )

    existing_tables = set(
        inspect(engine).get_table_names(
            schema="public"
        )
    )

    missing_tables = (
        expected_tables - existing_tables
    )

    if missing_tables:
        raise RuntimeError(
            "Production database schema is missing "
            f"{len(missing_tables)} required "
            "application table(s). "
            "Run an approved schema migration."
        )


# ==========================================================
# DATABASE SESSION CONTEXT MANAGER
# ==========================================================

@contextmanager
def get_db_session():
    """Provide a transactional SQLAlchemy session."""

    session = SessionLocal()

    try:

        yield session

        session.commit()

    except Exception:

        session.rollback()
        raise

    finally:

        session.close()
