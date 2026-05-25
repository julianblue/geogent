"""Auth boundary tests for the raster-compute endpoints.

Mirrors test_analytics_auth.py: strip the shared `get_current_user` override so
the HTTPBearer guard is actually exercised, then assert 401/403 unauthenticated.
"""

from uuid import uuid4

import pytest
from httpx import AsyncClient

from geogent_backend.api.deps import get_current_user
from geogent_backend.main import app


@pytest.fixture
async def unauth_client(client: AsyncClient) -> AsyncClient:
    """`client` with the `get_current_user` override stripped off."""
    app.dependency_overrides.pop(get_current_user, None)
    return client


@pytest.mark.asyncio
async def test_zonal_stats_requires_auth(unauth_client: AsyncClient) -> None:
    r = await unauth_client.post(
        "/api/v1/analytics/zonal-stats", json={"field_id": 1, "index": "ndvi"}
    )
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_time_series_requires_auth(unauth_client: AsyncClient) -> None:
    r = await unauth_client.post(
        "/api/v1/analytics/time-series",
        json={
            "field_id": 1,
            "index": "ndvi",
            "start_date": "2026-04-01",
            "end_date": "2026-09-30",
        },
    )
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_time_series_get_requires_auth(unauth_client: AsyncClient) -> None:
    r = await unauth_client.get(f"/api/v1/analytics/time-series/{uuid4()}")
    assert r.status_code in (401, 403)
