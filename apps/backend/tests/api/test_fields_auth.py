"""Auth boundary tests for /api/v1/fields/*.

The shared `client` fixture overrides `get_current_user`; these tests strip the
override so the HTTPBearer guard on the fields router is actually exercised.
"""

import pytest
from httpx import AsyncClient

from geogent_backend.api.deps import get_current_user
from geogent_backend.main import app

FIXTURE_POLYGON = {
    "type": "Polygon",
    "coordinates": [[[-93.65, 42.02], [-93.647, 42.02], [-93.647, 42.022], [-93.65, 42.02]]],
}


@pytest.fixture
async def unauth_client(client: AsyncClient) -> AsyncClient:
    app.dependency_overrides.pop(get_current_user, None)
    return client


@pytest.mark.asyncio
async def test_list_fields_requires_auth(unauth_client: AsyncClient) -> None:
    r = await unauth_client.get("/api/v1/fields")
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_create_field_requires_auth(unauth_client: AsyncClient) -> None:
    r = await unauth_client.post(
        "/api/v1/fields",
        json={"name": "North Forty", "geometry": FIXTURE_POLYGON},
    )
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_fields_in_bbox_requires_auth(unauth_client: AsyncClient) -> None:
    r = await unauth_client.get(
        "/api/v1/fields/in-bbox",
        params={"min_lon": -94.0, "min_lat": 41.0, "max_lon": -93.0, "max_lat": 43.0},
    )
    assert r.status_code in (401, 403)
