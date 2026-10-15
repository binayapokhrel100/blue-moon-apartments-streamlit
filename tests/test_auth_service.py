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
    """
    Unknown credentials must be rejected.

    Mock the SQLite transaction-lock implementation
    because this unit test uses a mocked DB session,
    not a real SQLAlchemy session.

    Actual transaction locking is covered separately
    by tests/test_auth_concurrency.py.
    """

    with (
        patch(
            "services.auth_service.get_db_session"
        ) as mock_session,
        patch(
            "services.auth_service.acquire_authentication_lock"
        ) as mock_lock,
    ):

        db = (
            mock_session
            .return_value
            .__enter__
            .return_value
        )

        # Simulate an unknown email address.
        db.scalar.return_value = None

        result = authenticate_user(
            "unknown@example.com",
            "incorrect",
        )

        assert result is None

        # Verify authentication still attempts
        # to acquire the transaction lock.
        mock_lock.assert_called_once_with(db)
