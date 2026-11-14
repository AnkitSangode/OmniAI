
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hashing():
    password = "StrongPassword123!"

    hashed = hash_password(password)

    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("WrongPassword123!", hashed)


def test_access_token_creation_and_decoding():
    user_id = "8b2e8d4f-1234-4567-8901-123456789abc"

    token = create_access_token(user_id)
    payload = decode_access_token(token)

    assert payload["sub"] == user_id
    assert payload["type"] == "access"
    assert "exp" in payload
    assert "iat" in payload
