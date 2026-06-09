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
    geo_tools,
    geometries_intersect,
    list_features,
    list_fields,
    seasonal_index_time_series_for_field,
    zonal_stats_for_field,
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
async def test_list_fields_calls_get(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request, captured: dict) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        return httpx.Response(200, json=[{"id": 7, "name": "North field", "crop": "wheat"}])

    captured = _install_mock_backend(monkeypatch, handler)
    result = await list_fields.ainvoke({})

    assert captured == {"method": "GET", "path": "/api/v1/fields"}
    assert result == [{"id": 7, "name": "North field", "crop": "wheat"}]


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


@pytest.mark.asyncio
async def test_zonal_stats_for_field_posts_schema_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request, captured: dict) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "field_id": 7,
                "index": "ndvi",
                "scene": {
                    "id": "S2B_31UDQ_20260501_0_L2A",
                    "datetime": "2026-05-01T10:30:00Z",
                    "cloud_cover": 4.2,
                    "epsg": 32631,
                },
                "stats": {
                    "mean": 0.63,
                    "min": 0.11,
                    "max": 0.92,
                    "std": 0.17,
                    "valid_pixels": 12034,
                    "nodata_pixels": 321,
                },
                "histogram": {"bin_edges": [-1.0, 0.0, 1.0], "counts": [20, 80]},
                "cached": True,
            },
        )

    captured = _install_mock_backend(monkeypatch, handler)
    result = await zonal_stats_for_field.ainvoke(
        {
            "field_id": 7,
            "index": "ndvi",
            "scene_id": "S2B_31UDQ_20260501_0_L2A",
            "datetime": "2026-05-01T10:30:00Z",
            "max_cloud_cover": 15,
            "histogram_bins": 32,
        }
    )

    assert captured["path"] == "/api/v1/analytics/zonal-stats"
    assert captured["body"] == {
        "field_id": 7,
        "index": "ndvi",
        "scene_id": "S2B_31UDQ_20260501_0_L2A",
        "datetime": "2026-05-01T10:30:00Z",
        "max_cloud_cover": 15,
        "histogram_bins": 32,
    }
    assert result["field_id"] == 7
    assert result["stats"]["mean"] == 0.63


@pytest.mark.asyncio
async def test_seasonal_time_series_starts_job_and_polls_until_succeeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count = {"polls": 0}

    def handler(request: httpx.Request, captured: dict) -> httpx.Response:
        captured.setdefault("requests", []).append((request.method, request.url.path))
        if request.method == "POST" and request.url.path == "/api/v1/analytics/time-series":
            captured["start_body"] = json.loads(request.content)
            return httpx.Response(
                202,
                json={"job_id": "11111111-1111-1111-1111-111111111111", "status": "pending"},
            )
        if (
            request.method == "GET"
            and request.url.path
            == "/api/v1/analytics/time-series/11111111-1111-1111-1111-111111111111"
        ):
            call_count["polls"] += 1
            if call_count["polls"] == 1:
                return httpx.Response(
                    200,
                    json={
                        "job_id": "11111111-1111-1111-1111-111111111111",
                        "status": "running",
                        "field_id": 7,
                        "index": "ndvi",
                        "params": {},
                        "points": [],
                        "error": None,
                    },
                )
            return httpx.Response(
                200,
                json={
                    "job_id": "11111111-1111-1111-1111-111111111111",
                    "status": "succeeded",
                    "field_id": 7,
                    "index": "ndvi",
                    "params": {"start_date": "2025-04-01", "end_date": "2025-09-30"},
                    "points": [
                        {
                            "scene_id": "S2A_31UDQ_20250412_0_L2A",
                            "datetime": "2025-04-12T10:30:00Z",
                            "cloud_cover": 6.1,
                            "mean": 0.51,
                            "min": 0.15,
                            "max": 0.81,
                            "std": 0.12,
                            "valid_pixels": 11700,
                        }
                    ],
                    "error": None,
                },
            )
        return httpx.Response(404, json={"detail": "unexpected path"})

    captured = _install_mock_backend(monkeypatch, handler)
    monkeypatch.setattr(geo_tools, "_TIME_SERIES_POLL_INTERVAL_SECONDS", 0)
    result = await seasonal_index_time_series_for_field.ainvoke(
        {
            "field_id": 7,
            "index": "ndvi",
            "start_date": "2025-04-01",
            "end_date": "2025-09-30",
            "max_cloud_cover": 20,
            "max_scenes": 60,
        }
    )

    assert captured["start_body"] == {
        "field_id": 7,
        "index": "ndvi",
        "start_date": "2025-04-01",
        "end_date": "2025-09-30",
        "max_cloud_cover": 20,
        "max_scenes": 60,
    }
    assert call_count["polls"] == 2
    assert result["status"] == "succeeded"
    assert result["points"][0]["scene_id"] == "S2A_31UDQ_20250412_0_L2A"


@pytest.mark.asyncio
async def test_seasonal_time_series_raises_on_failed_job(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request, _captured: dict) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                202,
                json={"job_id": "11111111-1111-1111-1111-111111111111", "status": "pending"},
            )
        return httpx.Response(
            200,
            json={
                "job_id": "11111111-1111-1111-1111-111111111111",
                "status": "failed",
                "field_id": 7,
                "index": "ndvi",
                "params": {},
                "points": [],
                "error": "boom",
            },
        )

    _install_mock_backend(monkeypatch, handler)
    monkeypatch.setattr(geo_tools, "_TIME_SERIES_POLL_INTERVAL_SECONDS", 0)

    with pytest.raises(RuntimeError, match="boom"):
        await seasonal_index_time_series_for_field.ainvoke(
            {
                "field_id": 7,
                "index": "ndvi",
                "start_date": "2025-04-01",
                "end_date": "2025-09-30",
            }
        )
