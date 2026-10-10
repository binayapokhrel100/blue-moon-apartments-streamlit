import os
from dotenv import load_dotenv

load_dotenv()

APP_NAME = os.getenv("APP_NAME", "Blue Moon Apartments")
APP_ENV = os.getenv("APP_ENV", "development")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///blue_moon.db")


def get_app_name():
    return os.getenv("APP_NAME", "Blue Moon Apartments")


def get_environment():
    return os.getenv("APP_ENV", "development")


def get_database_url():
    return os.getenv("DATABASE_URL", "sqlite:///blue_moon.db")


def get_secret_key():
    key = os.getenv("SECRET_KEY")

    if not key or key == "replace-this-with-a-secure-secret":
        raise ValueError("SECRET_KEY is not configured")

    return key
