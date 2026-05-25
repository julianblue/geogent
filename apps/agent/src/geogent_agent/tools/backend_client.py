import asyncio
import time
from collections.abc import AsyncGenerator

import httpx

from geogent_agent.config import get_settings

# Module-level token cache shared by every client returned from
# ``get_backend_client()``. ``_expires_at`` is a ``time.monotonic()`` deadline.
_token: str | None = None
_expires_at: float = 0.0
_lock = asyncio.Lock()


def _reset_token_cache() -> None:
    """Clear the cached service token. Intended for tests."""
    global _token, _expires_at
    _token = None
    _expires_at = 0.0


async def _login() -> tuple[str, int]:
    """Log in as the agent's service user and return ``(access_token, expires_in)``."""
    settings = get_settings()
    async with httpx.AsyncClient(base_url=settings.backend_url, timeout=30.0) as client:
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": settings.backend_service_email,
                "password": settings.backend_service_password,
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["access_token"], int(data["expires_in"])


async def _get_token(*, force_refresh: bool = False) -> str:
    """Return a valid service token, refreshing it (slightly early) when needed."""
    global _token, _expires_at
    async with _lock:
        if force_refresh or _token is None or time.monotonic() >= _expires_at:
            token, ttl = await _login()
            _token = token
            # Refresh a minute before the real expiry to avoid races at the edge,
            # but never schedule the deadline in the past for short-lived tokens.
            _expires_at = time.monotonic() + max(ttl - 60, 0)
        return _token


class _ServiceTokenAuth(httpx.Auth):
    """Attaches the cached service JWT and refreshes once on a 401."""

    async def async_auth_flow(
        self, request: httpx.Request
    ) -> AsyncGenerator[httpx.Request, httpx.Response]:
        request.headers["Authorization"] = f"Bearer {await _get_token()}"
        response = yield request
        if response.status_code == 401:
            # Drain the first response and retry on a freshly built request: the
            # original body stream may be consumed, and httpx.Request has no
            # .copy(), so reconstruct it from the buffered content.
            await response.aread()
            retry = httpx.Request(
                method=request.method,
                url=request.url,
                headers=request.headers,
                content=request.content,
                extensions=request.extensions,
            )
            retry.headers["Authorization"] = f"Bearer {await _get_token(force_refresh=True)}"
            yield retry


def get_backend_client() -> httpx.AsyncClient:
    settings = get_settings()
    return httpx.AsyncClient(
        base_url=settings.backend_url,
        timeout=30.0,
        auth=_ServiceTokenAuth(),
    )
