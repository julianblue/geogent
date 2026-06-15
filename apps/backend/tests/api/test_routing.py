"""Route tests for /api/v1/routing/* and /api/v1/geocode/*.

Monkeypatches the provider functions in ``geo/routing.py`` so the routes run
with no external network. Provider-layer URL/param construction is exercised
separately in ``tests/geo/test_routing.py``.
"""

import pytest
from httpx import AsyncClient

from geogent_backend.api.v1.routes import routing as routing_routes
from geogent_backend.geo.routing import IsochroneUnavailableError, RoutingError


@pytest.mark.asyncio
async def test_route_returns_summary_and_geometry(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_route(coords, profile):  # noqa: ANN001
        assert coords == [(2.35, 48.86), (2.13, 48.80)]
        assert profile == "driving"
        return {
            "distance_m": 21000.0,
            "duration_s": 1500.0,
            "geometry": {"type": "LineString", "coordinates": [[2.35, 48.86], [2.13, 48.80]]},
        }

    monkeypatch.setattr(routing_routes.routing_provider, "route", fake_route)

    r = await client.post(
        "/api/v1/routing/route",
        json={
            "coordinates": [
                {"longitude": 2.35, "latitude": 48.86},
                {"longitude": 2.13, "latitude": 48.80},
            ],
            "profile": "driving",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["distance_m"] == 21000.0
    assert body["geometry"]["type"] == "LineString"
    assert body["profile"] == "driving"


@pytest.mark.asyncio
async def test_route_upstream_failure_is_502(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_route(coords, profile):  # noqa: ANN001, ARG001
        raise RoutingError("No route found between the given points.")

    monkeypatch.setattr(routing_routes.routing_provider, "route", fake_route)

    r = await client.post(
        "/api/v1/routing/route",
        json={
            "coordinates": [
                {"longitude": 2.35, "latitude": 48.86},
                {"longitude": 2.13, "latitude": 48.80},
            ]
        },
    )
    assert r.status_code == 502
    assert "no route" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_route_rejects_single_coordinate(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/routing/route",
        json={"coordinates": [{"longitude": 2.35, "latitude": 48.86}]},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_matrix_returns_grids(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_matrix(coords, sources, destinations, profile):  # noqa: ANN001, ARG001
        return {
            "durations_s": [[0.0, 60.0], [60.0, 0.0]],
            "distances_m": [[0.0, 1000.0], [1000.0, 0.0]],
        }

    monkeypatch.setattr(routing_routes.routing_provider, "matrix", fake_matrix)

    r = await client.post(
        "/api/v1/routing/matrix",
        json={
            "coordinates": [
                {"longitude": 2.35, "latitude": 48.86},
                {"longitude": 2.13, "latitude": 48.80},
            ]
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["durations_s"] == [[0.0, 60.0], [60.0, 0.0]]


@pytest.mark.asyncio
async def test_isochrone_converts_minutes_to_seconds(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict = {}

    async def fake_iso(lon, lat, range_seconds, profile):  # noqa: ANN001
        seen["range_seconds"] = range_seconds
        return {"type": "FeatureCollection", "features": []}

    monkeypatch.setattr(routing_routes.routing_provider, "isochrone", fake_iso)

    r = await client.post(
        "/api/v1/routing/isochrone",
        json={"longitude": 2.29, "latitude": 48.85, "range_minutes": [5, 10]},
    )
    assert r.status_code == 200
    assert seen["range_seconds"] == [300, 600]
    assert r.json()["geojson"]["type"] == "FeatureCollection"


@pytest.mark.asyncio
async def test_isochrone_unconfigured_is_503(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_iso(lon, lat, range_seconds, profile):  # noqa: ANN001, ARG001
        raise IsochroneUnavailableError("Isochrones require an OpenRouteService key.")

    monkeypatch.setattr(routing_routes.routing_provider, "isochrone", fake_iso)

    r = await client.post(
        "/api/v1/routing/isochrone",
        json={"longitude": 2.29, "latitude": 48.85, "range_minutes": [10]},
    )
    assert r.status_code == 503


@pytest.mark.asyncio
async def test_geocode_returns_candidates(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_geocode(query, limit):  # noqa: ANN001
        assert query == "Eiffel Tower"
        return [
            {
                "display_name": "Eiffel Tower, Paris, France",
                "longitude": 2.2945,
                "latitude": 48.8584,
                "type": "attraction",
                "bbox": [2.29, 48.85, 2.30, 48.86],
            }
        ]

    monkeypatch.setattr(routing_routes.routing_provider, "geocode", fake_geocode)

    r = await client.get("/api/v1/geocode", params={"q": "Eiffel Tower"})
    assert r.status_code == 200
    results = r.json()["results"]
    assert results[0]["latitude"] == 48.8584


@pytest.mark.asyncio
async def test_reverse_geocode_returns_address(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_reverse(lon, lat):  # noqa: ANN001
        return {
            "display_name": "Champ de Mars, Paris",
            "longitude": lon,
            "latitude": lat,
            "type": "park",
            "address": {"city": "Paris", "country": "France"},
        }

    monkeypatch.setattr(routing_routes.routing_provider, "reverse_geocode", fake_reverse)

    r = await client.get("/api/v1/geocode/reverse", params={"lon": 2.2945, "lat": 48.8584})
    assert r.status_code == 200
    assert r.json()["address"]["city"] == "Paris"
