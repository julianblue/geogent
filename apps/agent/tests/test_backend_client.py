"""Unit tests for the authenticated backend HTTP client.

All traffic is served by ``httpx.MockTransport`` or by monkeypatching
``_login`` so the suite stays fully offline.
"""

import httpx
import pytest

from geogent_agent.config import get_settings
from geogent_agent.tools import backend_client
from geogent_agent.tools.backend_client import (
    _get_token,
    _reset_token_cache,
    _ServiceTokenAuth,
    get_backend_client,
)


@pytest.fixture(autouse=True)
def _clear_token_cache():
    """Ensure each test starts with an empty module-level token cache."""
    _reset_token_cache()
    yield
    _reset_token_cache()


async def test_auth_header_attached(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_login() -> tuple[str, int]:
        return "tok-123", 3600

    monkeypatch.setattr(backend_client, "_login", fake_login)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"authorization": request.headers.get("Authorization")})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://backend.test",
        auth=_ServiceTokenAuth(),
    )
    async with client:
        response = await client.get("/api/v1/features")

    assert response.json() == {"authorization": "Bearer tok-123"}


async def test_token_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    async def counting_login() -> tuple[str, int]:
        calls["n"] += 1
        return "cached-token", 3600

    monkeypatch.setattr(backend_client, "_login", counting_login)

    first = await _get_token()
    second = await _get_token()

    assert first == second == "cached-token"
    assert calls["n"] == 1


async def test_refresh_on_401(monkeypatch: pytest.MonkeyPatch) -> None:
    login_calls = {"n": 0}
    protected_calls = {"n": 0}

    async def counting_login() -> tuple[str, int]:
        login_calls["n"] += 1
        return f"token-{login_calls['n']}", 3600

    monkeypatch.setattr(backend_client, "_login", counting_login)

    def handler(request: httpx.Request) -> httpx.Response:
        protected_calls["n"] += 1
        if protected_calls["n"] == 1:
            return httpx.Response(401, json={"detail": "expired"})
        return httpx.Response(200, json={"authorization": request.headers.get("Authorization")})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://backend.test",
        auth=_ServiceTokenAuth(),
    )
    async with client:
        response = await client.get("/api/v1/features")

    assert response.status_code == 200
    # First login on the initial request, second login forced by the 401 retry.
    assert login_calls["n"] == 2
    assert protected_calls["n"] == 2
    assert response.json() == {"authorization": "Bearer token-2"}


async def test_get_backend_client_configuration() -> None:
    client = get_backend_client()
    async with client:
        assert isinstance(client.auth, _ServiceTokenAuth)
        assert str(client.base_url) == get_settings().backend_url
