"""Unit tests for the LangChain @tool wrappers in `geogent_agent.tools`.

We replace the real backend client with one driven by `httpx.MockTransport`
so tests don't require the backend to be running.
"""

import json

import httpx
import pytest

from geogent_agent.tools import (
    analyze_index_season,
    area_of,
    buffer_geometry,
    crop_stats_within_bbox,
    delineate_management_zones,
    distance_between,
    features_within,
    fields_within_bbox,
    geo_tools,
    geometries_intersect,
    list_features,
    list_fields,
    seasonal_index_time_series_for_field,
    temporal_features,
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


@pytest.mark.asyncio
async def test_field_memory_builds_and_polls_until_succeeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    polls = {"n": 0}

    def handler(request: httpx.Request, captured: dict) -> httpx.Response:
        captured.setdefault("requests", []).append((request.method, request.url.path))
        if request.method == "POST" and request.url.path == "/api/v1/analytics/temporal-features":
            captured["start_body"] = json.loads(request.content)
            return httpx.Response(
                202,
                json={
                    "artifact_id": "cafe1234",
                    "kind": "temporal_features",
                    "status": "pending",
                    "cached": False,
                },
            )
        if request.method == "GET" and request.url.path == "/api/v1/analytics/artifacts/cafe1234":
            polls["n"] += 1
            if polls["n"] == 1:
                return httpx.Response(200, json={"id": "cafe1234", "status": "running"})
            return httpx.Response(
                200,
                json={
                    "id": "cafe1234",
                    "kind": "temporal_features",
                    "status": "succeeded",
                    "summary": {
                        "index": "ndvi",
                        "n_scenes_used": 18,
                        "productivity": {"mean": 0.39, "within_field_spread": 0.17},
                        "stability": {"mean": 0.20, "within_field_spread": 0.11},
                    },
                    "assets": [{"role": "field_memory", "key": "field_memory.tif", "url": "/x"}],
                    "error": None,
                },
            )
        return httpx.Response(404, json={"detail": "unexpected path"})

    captured = _install_mock_backend(monkeypatch, handler)
    monkeypatch.setattr(geo_tools, "_ARTIFACT_POLL_INTERVAL_SECONDS", 0)

    result = await temporal_features.ainvoke(
        {
            "field_id": 7,
            "index": "ndvi",
            "start_date": "2024-04-01",
            "end_date": "2025-09-30",
        }
    )

    assert captured["start_body"]["field_id"] == 7
    assert polls["n"] == 2
    assert result["status"] == "succeeded"
    assert result["summary"]["productivity"]["within_field_spread"] == 0.17


@pytest.mark.asyncio
async def test_field_memory_raises_on_failed_build(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request, _captured: dict) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                202, json={"artifact_id": "dead", "kind": "temporal_features", "status": "pending"}
            )
        return httpx.Response(200, json={"id": "dead", "status": "failed", "error": "no scenes"})

    _install_mock_backend(monkeypatch, handler)
    monkeypatch.setattr(geo_tools, "_ARTIFACT_POLL_INTERVAL_SECONDS", 0)

    with pytest.raises(RuntimeError, match="no scenes"):
        await temporal_features.ainvoke(
            {"field_id": 7, "start_date": "2024-04-01", "end_date": "2025-09-30"}
        )


@pytest.mark.asyncio
async def test_list_fields_truncates_large_collections(monkeypatch: pytest.MonkeyPatch) -> None:
    many = [
        {
            "id": i,
            "name": f"DE-BB {i}",
            "crop": "winter_rye",
            "season": "2023",
            "geometry": {"type": "Polygon", "coordinates": []},
        }
        for i in range(120)
    ]

    def handler(request: httpx.Request, captured: dict) -> httpx.Response:
        return httpx.Response(200, json=many)

    _install_mock_backend(monkeypatch, handler)
    result = await list_fields.ainvoke({})

    assert result["truncated"] is True
    assert result["total_fields"] == 120
    assert len(result["fields"]) == 50
    # Compact rows: geometry stripped so the context stays small.
    assert "geometry" not in result["fields"][0]
    assert "fields_within_bbox" in result["note"]


@pytest.mark.asyncio
async def test_fields_within_bbox_forwards_params_and_compacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request, captured: dict) -> httpx.Response:
        captured["path"] = request.url.path
        captured["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            json=[
                {
                    "id": 201,
                    "name": "DE-BB X",
                    "crop": "winter_common_soft_wheat",
                    "season": "2023",
                    "geometry": {"type": "Polygon", "coordinates": []},
                    "created_at": "2026-01-01T00:00:00Z",
                }
            ],
        )

    captured = _install_mock_backend(monkeypatch, handler)
    result = await fields_within_bbox.ainvoke(
        {
            "min_lon": 13.75,
            "min_lat": 53.2,
            "max_lon": 14.05,
            "max_lat": 53.4,
            "crop": "wheat",
            "limit": 10,
        }
    )

    assert captured["path"] == "/api/v1/fields/in-bbox"
    assert captured["params"] == {
        "min_lon": "13.75",
        "min_lat": "53.2",
        "max_lon": "14.05",
        "max_lat": "53.4",
        "crop": "wheat",
        "limit": "10",
    }
    assert result == [
        {"id": 201, "name": "DE-BB X", "crop": "winter_common_soft_wheat", "season": "2023"}
    ]


@pytest.mark.asyncio
async def test_crop_stats_within_bbox(monkeypatch: pytest.MonkeyPatch) -> None:
    stats = [{"crop": "winter_common_soft_wheat", "parcels": 81, "total_area_ha": 1843.5}]

    def handler(request: httpx.Request, captured: dict) -> httpx.Response:
        captured["path"] = request.url.path
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json=stats)

    captured = _install_mock_backend(monkeypatch, handler)
    result = await crop_stats_within_bbox.ainvoke(
        {"min_lon": 13.75, "min_lat": 53.2, "max_lon": 14.05, "max_lat": 53.4}
    )

    assert captured["path"] == "/api/v1/fields/crop-stats"
    assert "crop" not in captured["params"]
    assert result == stats


@pytest.mark.asyncio
async def test_temporal_features_accepts_a_wkt_aoi(monkeypatch: pytest.MonkeyPatch) -> None:
    """An arbitrary polygon AOI reaches the recipe as geometry_wkt (M1.5)."""

    def handler(request: httpx.Request, captured: dict) -> httpx.Response:
        if request.method == "POST":
            captured["start_body"] = json.loads(request.content)
            return httpx.Response(
                202, json={"artifact_id": "a1", "kind": "temporal_features", "status": "pending"}
            )
        return httpx.Response(
            200,
            json={"id": "a1", "status": "succeeded", "summary": {"outputs": {}}, "assets": []},
        )

    captured = _install_mock_backend(monkeypatch, handler)
    monkeypatch.setattr(geo_tools, "_ARTIFACT_POLL_INTERVAL_SECONDS", 0)

    wkt = "POLYGON((13.9 53.3, 13.91 53.3, 13.91 53.31, 13.9 53.31, 13.9 53.3))"
    await temporal_features.ainvoke(
        {"geometry_wkt": wkt, "start_date": "2025-04-01", "end_date": "2025-09-30"}
    )

    assert captured["start_body"]["geometry_wkt"] == wkt
    assert "field_id" not in captured["start_body"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "aoi",
    [
        {},
        {"field_id": 7, "bbox": [13.9, 53.3, 13.91, 53.31]},
    ],
    ids=["no-aoi", "two-aois"],
)
async def test_temporal_features_requires_exactly_one_aoi(aoi: dict) -> None:
    """Zero or multiple AOIs fail in the tool with an actionable message rather
    than as an opaque backend 422."""
    with pytest.raises(ValueError, match="exactly one area of interest"):
        await temporal_features.ainvoke(
            {"start_date": "2025-04-01", "end_date": "2025-09-30", **aoi}
        )


@pytest.mark.asyncio
async def test_analyze_index_season_submits_and_polls(monkeypatch: pytest.MonkeyPatch) -> None:
    polls = {"n": 0}

    def handler(request: httpx.Request, captured: dict) -> httpx.Response:
        if request.method == "POST":
            captured["start_body"] = json.loads(request.content)
            return httpx.Response(202, json={"job_id": "job-1", "status": "pending"})
        polls["n"] += 1
        if polls["n"] == 1:
            return httpx.Response(200, json={"job_id": "job-1", "status": "running"})
        return httpx.Response(
            200,
            json={
                "job_id": "job-1",
                "status": "succeeded",
                "field_id": 7,
                "index": "ndvi",
                "params": {},
                "points": [],
                "curve": [{"date": "2025-06-01", "value": 0.71}],
                "phenology": {"status": "ok", "peak_date": "2025-06-20", "peak_value": 0.83},
                "anomaly": {"status": "ok", "mean_difference": -0.06},
                "error": None,
            },
        )

    captured = _install_mock_backend(monkeypatch, handler)
    monkeypatch.setattr(geo_tools, "_SEASON_ANALYSIS_POLL_INTERVAL_SECONDS", 0)

    result = await analyze_index_season.ainvoke(
        {
            "field_id": 7,
            "start_date": "2025-03-01",
            "end_date": "2025-10-31",
            "baseline_years": 2,
        }
    )

    assert captured["start_body"]["baseline_years"] == 2
    assert polls["n"] == 2  # polled past "running"
    assert result["phenology"]["peak_date"] == "2025-06-20"
    assert result["anomaly"]["mean_difference"] == -0.06


@pytest.mark.asyncio
async def test_analyze_index_season_raises_on_failed_job(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request, _captured: dict) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(202, json={"job_id": "job-2", "status": "pending"})
        return httpx.Response(
            200, json={"job_id": "job-2", "status": "failed", "error": "Season analysis failed."}
        )

    _install_mock_backend(monkeypatch, handler)
    monkeypatch.setattr(geo_tools, "_SEASON_ANALYSIS_POLL_INTERVAL_SECONDS", 0)

    with pytest.raises(RuntimeError, match="Season analysis failed"):
        await analyze_index_season.ainvoke(
            {"field_id": 7, "start_date": "2025-03-01", "end_date": "2025-10-31"}
        )


@pytest.mark.asyncio
async def test_delineate_management_zones_returns_the_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request, captured: dict) -> httpx.Response:
        if request.method == "POST":
            captured["start_body"] = json.loads(request.content)
            return httpx.Response(
                202, json={"artifact_id": "z1", "kind": "management_zones", "status": "pending"}
            )
        return httpx.Response(
            200,
            json={
                "id": "z1",
                "kind": "management_zones",
                "status": "succeeded",
                "summary": {
                    "n_zones": 3,
                    "zones": [{"zone": 1, "area_ha": 4.2, "share_of_area": 0.31}],
                    "attribution": [
                        {"feature": "ndvi_productivity", "variance_explained": 0.82},
                        {"feature": "ndvi_stability", "variance_explained": 0.11},
                    ],
                },
                "assets": [{"role": "zones", "key": "zones.tif", "url": "/x"}],
                "error": None,
            },
        )

    captured = _install_mock_backend(monkeypatch, handler)
    monkeypatch.setattr(geo_tools, "_ARTIFACT_POLL_INTERVAL_SECONDS", 0)

    result = await delineate_management_zones.ainvoke(
        {
            "field_id": 7,
            "start_date": "2023-04-01",
            "end_date": "2025-09-30",
            "indices": ["ndvi", "ndmi"],
        }
    )

    assert captured["start_body"]["indices"] == ["ndvi", "ndmi"]
    assert captured["start_body"]["n_zones"] is None  # auto by default
    assert result["summary"]["n_zones"] == 3
    assert result["summary"]["attribution"][0]["feature"] == "ndvi_productivity"


@pytest.mark.asyncio
async def test_delineate_management_zones_requires_one_aoi() -> None:
    with pytest.raises(ValueError, match="exactly one area of interest"):
        await delineate_management_zones.ainvoke(
            {"start_date": "2023-04-01", "end_date": "2025-09-30"}
        )
