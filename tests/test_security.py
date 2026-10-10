from core.security import (
    hash_password,
    verify_password,
)


def test_hash_password_does_not_store_plaintext():

    password = "BlueMoon123!"

    hashed = hash_password(password)

    assert hashed != password


def test_verify_password_accepts_correct_password():

    password = "BlueMoon123!"

    hashed = hash_password(password)

    assert verify_password(
        password,
        hashed,
    ) is True


def test_verify_password_rejects_wrong_password():

    hashed = hash_password(
        "BlueMoon123!"
    )

    assert verify_password(
        "WrongPassword",
        hashed,
    ) is False


def test_empty_password_returns_false():

    assert verify_password(
        "",
        "",
    ) is False