import os

from dotenv import load_dotenv


load_dotenv()


APP_NAME = os.getenv("APP_NAME", "Blue Moon Apartments")
APP_ENV = os.getenv("APP_ENV", "development")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///blue_moon.db",
)

SECRET_KEY = os.getenv(
    "SECRET_KEY",
    "development-secret-key",
)


def get_app_name() -> str:
    return APP_NAME


def get_environment() -> str:
    return APP_ENV