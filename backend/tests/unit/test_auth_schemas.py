
import pytest
from pydantic import ValidationError

from app.schemas.auth import (
    UserLoginRequest,
    UserRegisterRequest,
)


def test_valid_registration_request():
    payload = UserRegisterRequest(
        full_name="Test User",
        email="test@example.com",
        password="StrongPassword123!",
    )

    assert payload.full_name == "Test User"
    assert payload.email == "test@example.com"


def test_registration_rejects_invalid_email():
    with pytest.raises(ValidationError):
        UserRegisterRequest(
            full_name="Test User",
            email="invalid-email",
            password="StrongPassword123!",
        )


def test_registration_rejects_short_password():
    with pytest.raises(ValidationError):
        UserRegisterRequest(
            full_name="Test User",
            email="test@example.com",
            password="123",
        )


def test_valid_login_request():
    payload = UserLoginRequest(
        email="test@example.com",
        password="StrongPassword123!",
    )

    assert payload.email == "test@example.com"
