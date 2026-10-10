from unittest.mock import patch

from services.auth_service import authenticate_user


def test_empty_email():
    assert authenticate_user("", "password") is None


def test_empty_password():
    assert authenticate_user(
        "sarah.mitchell@bluemoon.demo",
        "",
    ) is None


def test_unknown_user():
    with patch(
        "services.auth_service.get_db_session"
    ) as mock_session:
        db = mock_session.return_value.__enter__.return_value
        db.scalar.return_value = None

        result = authenticate_user(
            "unknown@example.com",
            "incorrect",
        )

        assert result is None