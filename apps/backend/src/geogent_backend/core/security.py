from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from geogent_backend.config import get_settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


class TokenDecodeError(Exception):
    """Raised when a JWT fails signature, expiry, or payload validation."""


def create_access_token(
    subject: str | int, expires_minutes: int | None = None
) -> tuple[str, int]:
    """Returns ``(jwt, ttl_seconds)``."""
    settings = get_settings()
    minutes = expires_minutes if expires_minutes is not None else settings.jwt_access_token_expire_minutes
    expire = datetime.now(UTC) + timedelta(minutes=minutes)
    payload: dict[str, Any] = {"sub": str(subject), "exp": expire}
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, minutes * 60


def decode_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise TokenDecodeError(str(exc)) from exc
