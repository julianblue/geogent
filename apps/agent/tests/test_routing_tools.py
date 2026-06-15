"""Unit tests for the routing/geocoding @tool wrappers (#55).

Like test_tools.py, the backend client is replaced with one driven by
``httpx.MockTransport`` so no backend is required.
"""

import json

import httpx
import pytest

from geogent_agent.tools import (
    isochrone_for,
    reverse_geocode,
    route_between,
    travel_time_matrix,
)


def _install_mock_backend(monkeypatch: pytest.MonkeyPatch, handler) -> dict:
    captured: dict = {}

    def make_client() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.MockTransport(lambda req: handler(req, captured)),
            base_url="http://backend.test",
        )

    monkeypatch.setattr("geogent_agent.tools.routing_tools.get_backend_client", make_client)
    return captured


@pytest.mark.asyncio
async def test_route_between_summarises_km_and_minutes(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request, captured: dict) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "distance_m": 21340.0,
                "duration_s": 1530.0,
                "profile": "driving",
                "geometry": {"type": "LineString", "coordinates": [[2.35, 48.86], [2.13, 48.80]]},
            },
        )

    captured = _install_mock_backend(monkeypatch, handler)
    result = await route_between.ainvoke(
        {
            "origin_lon": 2.35,
            "origin_lat": 48.86,
            "dest_lon": 2.13,
            "dest_lat": 48.80,
            "profile": "driving",
        }
    )

    assert captured["path"] == "/api/v1/routing/route"
    assert captured["body"]["coordinates"][0] == {"longitude": 2.35, "latitude": 48.86}
    assert result["distance_km"] == 21.34
    assert result["duration_min"] == 25.5
    assert result["geometry"]["type"] == "LineString"


@pytest.mark.asyncio
async def test_travel_time_matrix_scales_units(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request, captured: dict) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "durations_s": [[0.0, 120.0], [120.0, None]],
                "distances_m": [[0.0, 2000.0], [2000.0, None]],
                "profile": "driving",
            },
        )

    captured = _install_mock_backend(monkeypatch, handler)
    result = await travel_time_matrix.ainvoke({"points": [[2.35, 48.86], [2.13, 48.80]]})

    assert captured["path"] == "/api/v1/routing/matrix"
    assert captured["body"]["coordinates"] == [
        {"longitude": 2.35, "latitude": 48.86},
        {"longitude": 2.13, "latitude": 48.80},
    ]
    assert result["durations_min"] == [[0.0, 2.0], [2.0, None]]
    assert result["distances_km"] == [[0.0, 2.0], [2.0, None]]


@pytest.mark.asyncio
async def test_isochrone_for_defaults_to_ten_minutes(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request, captured: dict) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "profile": "driving",
                "range_minutes": [10],
                "geojson": {"type": "FeatureCollection", "features": []},
            },
        )

    captured = _install_mock_backend(monkeypatch, handler)
    result = await isochrone_for.ainvoke({"longitude": 2.29, "latitude": 48.85})

    assert captured["body"]["range_minutes"] == [10]
    assert result["geojson"]["type"] == "FeatureCollection"


@pytest.mark.asyncio
async def test_reverse_geocode_forwards_coords(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request, captured: dict) -> httpx.Response:
        captured["path"] = request.url.path
        captured["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            json={
                "display_name": "Champ de Mars, Paris",
                "longitude": 2.2945,
                "latitude": 48.8584,
                "type": "park",
                "address": {"city": "Paris"},
            },
        )

    captured = _install_mock_backend(monkeypatch, handler)
    result = await reverse_geocode.ainvoke({"longitude": 2.2945, "latitude": 48.8584})

    assert captured["path"] == "/api/v1/geocode/reverse"
    assert captured["params"] == {"lon": "2.2945", "lat": "48.8584"}
    assert result["address"]["city"] == "Paris"


@pytest.mark.asyncio
async def test_route_between_raises_on_backend_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_request: httpx.Request, _captured: dict) -> httpx.Response:
        return httpx.Response(502, json={"detail": "No route found."})

    _install_mock_backend(monkeypatch, handler)

    with pytest.raises(httpx.HTTPStatusError):
        await route_between.ainvoke(
            {"origin_lon": 0.0, "origin_lat": 0.0, "dest_lon": 1.0, "dest_lat": 1.0}
        )
