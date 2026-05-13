"""Auth boundary tests for /api/v1/analytics/*.

The shared `client` fixture overrides `get_current_user` to a stub so the
analytics behaviour tests (test_analytics.py) don't need to forge JWTs. These
tests remove that override so we actually exercise the HTTPBearer guard.
"""

import pytest
from httpx import AsyncClient

from geogent_backend.api.deps import get_current_user
from geogent_backend.main import app


@pytest.fixture
async def unauth_client(client: AsyncClient) -> AsyncClient:
    """`client` with the `get_current_user` override stripped off."""
    app.dependency_overrides.pop(get_current_user, None)
    return client


@pytest.mark.parametrize(
    "path,payload",
    [
        ("/api/v1/analytics/buffer", {"geometry_wkt": "POINT(0 0)", "distance_m": 1.0}),
        ("/api/v1/analytics/distance", {"a_wkt": "POINT(0 0)", "b_wkt": "POINT(1 0)"}),
        ("/api/v1/analytics/area", {"geometry_wkt": "POLYGON((0 0,1 0,1 1,0 1,0 0))"}),
        ("/api/v1/analytics/intersects", {"a_wkt": "POINT(0 0)", "b_wkt": "POINT(0 0)"}),
        (
            "/api/v1/analytics/features-within",
            {"geometry_wkt": "POLYGON((0 0,1 0,1 1,0 1,0 0))"},
        ),
    ],
)
@pytest.mark.asyncio
async def test_analytics_requires_auth(
    unauth_client: AsyncClient, path: str, payload: dict
) -> None:
    r = await unauth_client.post(path, json=payload)
    # HTTPBearer (auto_error=True) returns 403 when the header is missing;
    # a present-but-invalid token returns 401. Either is acceptable here.
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_analytics_rejects_invalid_token(unauth_client: AsyncClient) -> None:
    r = await unauth_client.post(
        "/api/v1/analytics/buffer",
        json={"geometry_wkt": "POINT(0 0)", "distance_m": 1.0},
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    assert r.status_code == 401
