from sqlalchemy.ext.asyncio import AsyncSession

from geogent_backend.core.security import create_access_token, hash_password, verify_password
from geogent_backend.models.user import User
from geogent_backend.repositories.user_repo import UserRepository
from geogent_backend.schemas.auth import TokenResponse
from geogent_backend.schemas.user import UserCreate


class AuthError(Exception):
    """Raised for invalid credentials or signup conflicts."""


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self._users = UserRepository(session)

    async def authenticate(self, email: str, password: str) -> User:
        user = await self._users.get_by_email(email)
        if (
            user is None
            or not user.is_active
            or not verify_password(password, user.hashed_password)
        ):
            raise AuthError("Invalid credentials")
        return user

    def issue_token(self, user: User) -> TokenResponse:
        token, ttl = create_access_token(user.id)
        return TokenResponse(access_token=token, expires_in=ttl)

    async def create_user(self, payload: UserCreate) -> User:
        if await self._users.get_by_email(payload.email) is not None:
            raise AuthError("Email already registered")
        return await self._users.create(payload.email, hash_password(payload.password))
