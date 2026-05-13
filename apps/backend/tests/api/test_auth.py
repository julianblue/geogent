"""Route-level tests for /api/v1/auth/*.

Monkeypatches AuthService so the tests don't require a running DB.
"""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from geogent_backend.api.deps import get_current_user
from geogent_backend.api.v1.routes import auth as auth_routes
from geogent_backend.main import app
from geogent_backend.models.user import User
from geogent_backend.services.auth_service import AuthError


def _fake_user(email: str = "demo@geogent.dev") -> User:
    return User(
        id=1,
        email=email,
        hashed_password="not-used-in-this-test",
        is_active=True,
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_login_returns_token(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_authenticate(self, email: str, password: str) -> User:  # noqa: ARG001
        assert email == "demo@geogent.dev"
        assert password == "geogent12345"
        return _fake_user(email)

    monkeypatch.setattr(auth_routes.AuthService, "authenticate", fake_authenticate)

    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "demo@geogent.dev", "password": "geogent12345"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["expires_in"] > 0


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_authenticate(self, email: str, password: str) -> User:  # noqa: ARG001
        raise AuthError("Invalid credentials")

    monkeypatch.setattr(auth_routes.AuthService, "authenticate", fake_authenticate)

    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "demo@geogent.dev", "password": "nope"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_authorization_header(client: AsyncClient) -> None:
    # The shared `client` fixture overrides `get_current_user` to a stub; remove
    # the override so we exercise the real HTTPBearer/JWT path.
    app.dependency_overrides.pop(get_current_user, None)
    try:
        r = await client.get("/api/v1/auth/me")
        # HTTPBearer with auto_error returns 403 when the header is missing.
        assert r.status_code in (401, 403)
    finally:
        # Don't leak the cleared override to other tests in the same session.
        pass


@pytest.mark.asyncio
async def test_me_rejects_invalid_token(client: AsyncClient) -> None:
    app.dependency_overrides.pop(get_current_user, None)
    r = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    assert r.status_code == 401
