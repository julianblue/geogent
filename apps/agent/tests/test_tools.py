"""Unit tests for the LangChain @tool wrappers in `geogent_agent.tools`.

We replace the real backend client with one driven by `httpx.MockTransport`
so tests don't require the backend to be running.
"""

import json

import httpx
import pytest

from geogent_agent.tools import (
    area_of,
    buffer_geometry,
    distance_between,
    features_within,
    geometries_intersect,
    list_features,
)


def _install_mock_backend(monkeypatch: pytest.MonkeyPatch, handler) -> dict:
    """Replace `get_backend_client` with one routed through MockTransport.

    Returns a dict the handler can read/write to record requests for assertions.
    """
    captured: dict = {}

    def make_client() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.MockTransport(lambda req: handler(req, captured)),
            base_url="http://backend.test",
        )

    monkeypatch.setattr("geogent_agent.tools.geo_tools.get_backend_client", make_client)
    return captured


@pytest.mark.asyncio
async def test_list_features_calls_get(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request, captured: dict) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        return httpx.Response(200, json=[{"id": 1, "name": "alpha"}])

    captured = _install_mock_backend(monkeypatch, handler)
    result = await list_features.ainvoke({})

    assert captured == {"method": "GET", "path": "/api/v1/features"}
    assert result == [{"id": 1, "name": "alpha"}]


@pytest.mark.asyncio
async def test_buffer_geometry_posts_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request, captured: dict) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"buffered_wkt": "POLYGON(...)"})

    captured = _install_mock_backend(monkeypatch, handler)
    result = await buffer_geometry.ainvoke({"geometry_wkt": "POINT(0 0)", "distance_m": 100.0})

    assert captured["path"] == "/api/v1/analytics/buffer"
    assert captured["body"] == {"geometry_wkt": "POINT(0 0)", "distance_m": 100.0}
    assert result == "POLYGON(...)"


@pytest.mark.asyncio
async def test_distance_between_returns_meters(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request, captured: dict) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"distance_m": 4123456.7})

    captured = _install_mock_backend(monkeypatch, handler)
    result = await distance_between.ainvoke(
        {"a_wkt": "POINT(-122.42 37.77)", "b_wkt": "POINT(-73.98 40.75)"}
    )

    assert captured["path"] == "/api/v1/analytics/distance"
    assert captured["body"] == {
        "a_wkt": "POINT(-122.42 37.77)",
        "b_wkt": "POINT(-73.98 40.75)",
    }
    assert result == 4123456.7


@pytest.mark.asyncio
async def test_area_of_returns_square_meters(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request, captured: dict) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"area_m2": 12345.6})

    captured = _install_mock_backend(monkeypatch, handler)
    result = await area_of.ainvoke({"geometry_wkt": "POLYGON((0 0,1 0,1 1,0 1,0 0))"})

    assert captured["path"] == "/api/v1/analytics/area"
    assert captured["body"] == {"geometry_wkt": "POLYGON((0 0,1 0,1 1,0 1,0 0))"}
    assert result == 12345.6


@pytest.mark.asyncio
async def test_geometries_intersect_returns_bool(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request, captured: dict) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, json={"intersects": True})

    captured = _install_mock_backend(monkeypatch, handler)
    result = await geometries_intersect.ainvoke({"a_wkt": "POINT(0 0)", "b_wkt": "POINT(0 0)"})

    assert captured["path"] == "/api/v1/analytics/intersects"
    assert result is True


@pytest.mark.asyncio
async def test_features_within_returns_refs(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request, captured: dict) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(
            200,
            json={"features": [{"id": 1, "name": "alpha"}, {"id": 2, "name": "beta"}]},
        )

    captured = _install_mock_backend(monkeypatch, handler)
    result = await features_within.ainvoke({"geometry_wkt": "POLYGON((0 0,1 0,1 1,0 1,0 0))"})

    assert captured["path"] == "/api/v1/analytics/features-within"
    assert result == [{"id": 1, "name": "alpha"}, {"id": 2, "name": "beta"}]


@pytest.mark.asyncio
async def test_buffer_raises_on_backend_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_request: httpx.Request, _captured: dict) -> httpx.Response:
        return httpx.Response(500, json={"detail": "boom"})

    _install_mock_backend(monkeypatch, handler)

    with pytest.raises(httpx.HTTPStatusError):
        await buffer_geometry.ainvoke({"geometry_wkt": "POINT(0 0)", "distance_m": 100.0})
