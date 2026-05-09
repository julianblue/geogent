"""Route-level tests for /api/v1/analytics/*.

These tests monkeypatch the geo-operation functions imported into the route
module so they don't require a running PostGIS. The migrations smoke-test job
covers schema/SQL correctness against a real database.
"""

import pytest
from httpx import AsyncClient

from geogent_backend.api.v1.routes import analytics


@pytest.mark.asyncio
async def test_buffer_returns_wkt(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_buffer(_session, wkt: str, distance_m: float) -> str:
        return f"BUFFERED({wkt}, {distance_m})"

    monkeypatch.setattr(analytics, "buffer_geometry", fake_buffer)

    r = await client.post(
        "/api/v1/analytics/buffer",
        json={"geometry_wkt": "POINT(0 0)", "distance_m": 100.0},
    )
    assert r.status_code == 200
    assert r.json() == {"buffered_wkt": "BUFFERED(POINT(0 0), 100.0)"}


@pytest.mark.asyncio
async def test_buffer_rejects_non_positive_distance(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/analytics/buffer",
        json={"geometry_wkt": "POINT(0 0)", "distance_m": 0},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_distance_returns_meters(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_distance(_session, a: str, b: str) -> float:
        assert a == "POINT(0 0)"
        assert b == "POINT(1 0)"
        return 111195.0

    monkeypatch.setattr(analytics, "distance_between", fake_distance)

    r = await client.post(
        "/api/v1/analytics/distance",
        json={"a_wkt": "POINT(0 0)", "b_wkt": "POINT(1 0)"},
    )
    assert r.status_code == 200
    assert r.json() == {"distance_m": 111195.0}


@pytest.mark.asyncio
async def test_distance_rejects_missing_field(client: AsyncClient) -> None:
    r = await client.post("/api/v1/analytics/distance", json={"a_wkt": "POINT(0 0)"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_area_returns_square_meters(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_area(_session, wkt: str) -> float:
        assert wkt.startswith("POLYGON")
        return 12345.6

    monkeypatch.setattr(analytics, "area_of", fake_area)

    r = await client.post(
        "/api/v1/analytics/area",
        json={"geometry_wkt": "POLYGON((0 0,1 0,1 1,0 1,0 0))"},
    )
    assert r.status_code == 200
    assert r.json() == {"area_m2": 12345.6}


@pytest.mark.asyncio
async def test_intersects_returns_bool(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_intersects(_session, a: str, b: str) -> bool:
        return True

    monkeypatch.setattr(analytics, "geometries_intersect", fake_intersects)

    r = await client.post(
        "/api/v1/analytics/intersects",
        json={"a_wkt": "POINT(0 0)", "b_wkt": "POINT(0 0)"},
    )
    assert r.status_code == 200
    assert r.json() == {"intersects": True}


@pytest.mark.asyncio
async def test_features_within_returns_refs(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_features_within(_session, wkt: str) -> list[dict]:
        assert wkt.startswith("POLYGON")
        return [{"id": 1, "name": "alpha"}, {"id": 2, "name": "beta"}]

    monkeypatch.setattr(analytics, "features_within", fake_features_within)

    r = await client.post(
        "/api/v1/analytics/features-within",
        json={"geometry_wkt": "POLYGON((0 0,1 0,1 1,0 1,0 0))"},
    )
    assert r.status_code == 200
    assert r.json() == {"features": [{"id": 1, "name": "alpha"}, {"id": 2, "name": "beta"}]}
