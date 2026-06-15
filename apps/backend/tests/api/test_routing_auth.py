"""Auth boundary tests for /api/v1/routing/* and /api/v1/geocode/*.

Mirrors test_analytics_auth.py: strip the stub-user override so the HTTPBearer
guard is actually exercised.
"""

import pytest
from httpx import AsyncClient

from geogent_backend.api.deps import get_current_user
from geogent_backend.main import app


@pytest.fixture
async def unauth_client(client: AsyncClient) -> AsyncClient:
    app.dependency_overrides.pop(get_current_user, None)
    return client


@pytest.mark.parametrize(
    "method,path,kwargs",
    [
        (
            "post",
            "/api/v1/routing/route",
            {
                "json": {
                    "coordinates": [
                        {"longitude": 0.0, "latitude": 0.0},
                        {"longitude": 1.0, "latitude": 1.0},
                    ]
                }
            },
        ),
        (
            "post",
            "/api/v1/routing/matrix",
            {
                "json": {
                    "coordinates": [
                        {"longitude": 0.0, "latitude": 0.0},
                        {"longitude": 1.0, "latitude": 1.0},
                    ]
                }
            },
        ),
        (
            "post",
            "/api/v1/routing/isochrone",
            {"json": {"longitude": 0.0, "latitude": 0.0, "range_minutes": [10]}},
        ),
        ("get", "/api/v1/geocode", {"params": {"q": "Paris"}}),
        ("get", "/api/v1/geocode/reverse", {"params": {"lon": 0.0, "lat": 0.0}}),
    ],
)
@pytest.mark.asyncio
async def test_routing_requires_auth(
    unauth_client: AsyncClient, method: str, path: str, kwargs: dict
) -> None:
    r = await getattr(unauth_client, method)(path, **kwargs)
    # Missing bearer → 403 (HTTPBearer auto_error); invalid token → 401.
    assert r.status_code in (401, 403)
