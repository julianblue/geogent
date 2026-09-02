"""Route tests for the season-analysis endpoints.

Same shape as ``test_raster_time_series.py``: the service is monkeypatched so
the routes run with no network/DB. Covers the 202 submit, the poll payload, the
404 for an unknown job, and the schema validation that keeps an unbounded
baseline request from ever reaching the scene fan-out.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from geogent_backend.api.v1.routes import raster as raster_routes
from geogent_backend.schemas.raster import (
    CurvePoint,
    IndexName,
    JobStatus,
    SeasonAnalysisJobResponse,
    SeasonAnalysisResultResponse,
    TimeSeriesPoint,
)

_JOB_ID = uuid4()


@pytest.mark.asyncio
async def test_start_season_analysis_returns_202(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_start(self, req, background_tasks) -> SeasonAnalysisJobResponse:  # noqa: ANN001, ARG001
        assert req.field_id == 4
        assert req.baseline_years == 3
        assert req.index is IndexName.ndre
        return SeasonAnalysisJobResponse(job_id=_JOB_ID, status=JobStatus.pending)

    monkeypatch.setattr(raster_routes.RasterService, "start_season_analysis", fake_start)

    r = await client.post(
        "/api/v1/analytics/season-analysis",
        json={
            "field_id": 4,
            "index": "ndre",
            "start_date": "2026-04-01",
            "end_date": "2026-09-30",
            "baseline_years": 3,
        },
    )

    assert r.status_code == 202
    assert UUID(r.json()["job_id"]) == _JOB_ID


@pytest.mark.asyncio
async def test_get_season_analysis_returns_metrics_and_anomaly(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_get(self, job_id) -> SeasonAnalysisResultResponse:  # noqa: ANN001, ARG001
        return SeasonAnalysisResultResponse(
            job_id=_JOB_ID,
            status=JobStatus.succeeded,
            field_id=4,
            index=IndexName.ndvi,
            params={},
            points=[
                TimeSeriesPoint(
                    scene_id="S2B_1",
                    datetime=datetime(2026, 5, 1, tzinfo=UTC),
                    cloud_cover=3.0,
                    mean=0.62,
                    min=0.2,
                    max=0.9,
                    std=0.1,
                    valid_pixels=12000,
                )
            ],
            curve=[CurvePoint(date="2026-05-01", value=0.62)],
            phenology={"status": "ok", "peak_value": 0.81, "peak_date": "2026-06-20"},
            anomaly={"status": "ok", "mean_difference": -0.08, "baseline_years": [2024, 2025]},
        )

    monkeypatch.setattr(raster_routes.RasterService, "get_season_analysis", fake_get)

    r = await client.get(f"/api/v1/analytics/season-analysis/{_JOB_ID}")

    assert r.status_code == 200
    body = r.json()
    assert body["phenology"]["peak_date"] == "2026-06-20"
    assert body["anomaly"]["mean_difference"] == -0.08
    assert body["curve"] == [{"date": "2026-05-01", "value": 0.62}]


@pytest.mark.asyncio
async def test_get_season_analysis_unknown_job_is_404(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_get(self, job_id) -> None:  # noqa: ANN001, ARG001
        return None

    monkeypatch.setattr(raster_routes.RasterService, "get_season_analysis", fake_get)

    r = await client.get(f"/api/v1/analytics/season-analysis/{uuid4()}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_baseline_years_is_capped_at_the_schema(client: AsyncClient) -> None:
    """Each baseline year multiplies the scenes read, so an unbounded request is
    a 422 rather than a very expensive job."""
    r = await client.post(
        "/api/v1/analytics/season-analysis",
        json={
            "field_id": 4,
            "start_date": "2026-04-01",
            "end_date": "2026-09-30",
            "baseline_years": 25,
        },
    )
    assert r.status_code == 422
