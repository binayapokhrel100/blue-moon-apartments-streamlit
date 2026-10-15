
"""Application configuration for Blue Moon Apartments.

Development retains local defaults.

Production requires explicitly configured secrets
and a database URL.
"""

import os

from dotenv import load_dotenv


# ==================================================
# LOAD LOCAL ENVIRONMENT
# ==================================================

# Existing operating-system environment variables
# take precedence over values in .env.
load_dotenv(override=False)


# ==================================================
# APPLICATION SETTINGS
# ==================================================

APP_NAME = (
    os.getenv("APP_NAME", "Blue Moon Apartments").strip()
    or "Blue Moon Apartments"
)

APP_ENV = (
    os.getenv("APP_ENV", "development").strip().lower()
    or "development"
)

IS_PRODUCTION = APP_ENV in {
    "production",
    "prod",
}


# ==================================================
# DATABASE CONFIGURATION
# ==================================================

_configured_database_url = (
    os.getenv("DATABASE_URL", "").strip()
)

if IS_PRODUCTION:

    if not _configured_database_url:
        raise RuntimeError(
            "DATABASE_URL must be explicitly configured "
            "for the production environment."
        )

    DATABASE_URL = _configured_database_url

else:

    DATABASE_URL = (
        _configured_database_url
        or "sqlite:///blue_moon.db"
    )


# ==================================================
# APPLICATION SECRET
# ==================================================

_configured_secret_key = os.getenv(
    "SECRET_KEY",
    "",
)

if IS_PRODUCTION:

    if (
        not _configured_secret_key
        or len(_configured_secret_key.encode("utf-8")) < 32
        or _configured_secret_key.strip()
        != _configured_secret_key
        or _configured_secret_key
        == "development-secret-key"
    ):
        raise RuntimeError(
            "Production SECRET_KEY must be a securely "
            "generated value of at least 32 bytes. "
            "The development default is not allowed."
        )

    SECRET_KEY = _configured_secret_key

else:

    SECRET_KEY = (
        _configured_secret_key
        or "development-secret-key"
    )


# ==================================================
# PUBLIC CONFIGURATION HELPERS
# ==================================================

def get_app_name() -> str:
    """Return the configured application name."""

    return APP_NAME


def get_environment() -> str:
    """Return the configured runtime environment."""

    return APP_ENV
