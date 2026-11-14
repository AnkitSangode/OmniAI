
from fastapi import HTTPException, status

from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import UserLoginRequest, UserRegisterRequest


class AuthService:
    def __init__(self, user_repository: UserRepository):
        self.user_repository = user_repository

    async def register(self, payload: UserRegisterRequest) -> tuple[User, str]:
        email = str(payload.email).strip().lower()

        existing_user = await self.user_repository.get_by_email(email)

        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists.",
            )

        hashed_password = hash_password(payload.password)

        user = await self.user_repository.create(
            email=email,
            full_name=payload.full_name.strip(),
            hashed_password=hashed_password,
        )

        token = create_access_token(str(user.id))

        return user, token

    async def login(self, payload: UserLoginRequest) -> tuple[User, str]:
        email = str(payload.email).strip().lower()

        user = await self.user_repository.get_by_email(email)

        if not user or not verify_password(
            payload.password,
            user.hashed_password,
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This account is inactive.",
            )

        token = create_access_token(str(user.id))

        return user, token
