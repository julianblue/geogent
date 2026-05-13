from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from geogent_backend.api.deps import get_current_user
from geogent_backend.main import app
from geogent_backend.models.user import User


def _stub_user() -> User:
    return User(
        id=1,
        email="test@geogent.dev",
        hashed_password="not-used-in-tests",
        is_active=True,
        created_at=datetime.now(UTC),
    )


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """ASGI client with `get_current_user` overridden to a stub user.

    The override applies to every test that uses this fixture so analytics and
    other gated routes can be exercised without forging real JWTs. Tests that
    need to exercise the auth boundary itself (e.g. `test_auth.py`) should
    either remove the override locally or hit unauthenticated routes that the
    override doesn't affect.
    """
    app.dependency_overrides[get_current_user] = _stub_user
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_current_user, None)
