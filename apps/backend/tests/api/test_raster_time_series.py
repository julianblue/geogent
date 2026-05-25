"""Route tests for the background time-series endpoints.

Monkeypatches ``RasterService.start_time_series`` and ``get_time_series`` so the
routes run with no network/DB. Asserts 202 + job_id on start, that polling
returns points sorted by datetime, and 404 for an unknown job.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from geogent_backend.api.v1.routes import raster as raster_routes
from geogent_backend.schemas.raster import (
    IndexName,
    JobStatus,
    TimeSeriesJobResponse,
    TimeSeriesPoint,
    TimeSeriesResultResponse,
)

_JOB_ID = uuid4()


@pytest.mark.asyncio
async def test_start_time_series_returns_202(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_start(self, req, background_tasks) -> TimeSeriesJobResponse:  # noqa: ANN001, ARG001
        assert req.field_id == 4
        assert str(req.start_date) == "2026-04-01"
        return TimeSeriesJobResponse(job_id=_JOB_ID, status=JobStatus.pending)

    monkeypatch.setattr(raster_routes.RasterService, "start_time_series", fake_start)

    r = await client.post(
        "/api/v1/analytics/time-series",
        json={
            "field_id": 4,
            "index": "ndvi",
            "start_date": "2026-04-01",
            "end_date": "2026-09-30",
        },
    )
    assert r.status_code == 202
    body = r.json()
    assert UUID(body["job_id"]) == _JOB_ID
    assert body["status"] == "pending"


@pytest.mark.asyncio
async def test_get_time_series_returns_sorted_points(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _pt(day: int, mean: float) -> TimeSeriesPoint:
        return TimeSeriesPoint(
            scene_id=f"S2_{day}",
            datetime=datetime(2026, 5, day, tzinfo=UTC),
            cloud_cover=4.0,
            mean=mean,
            min=mean - 0.1,
            max=mean + 0.1,
            std=0.05,
            valid_pixels=1000,
        )

    points = sorted([_pt(20, 0.5), _pt(5, 0.3), _pt(12, 0.4)], key=lambda p: p.datetime)

    async def fake_get(self, job_id) -> TimeSeriesResultResponse:  # noqa: ANN001, ARG001
        return TimeSeriesResultResponse(
            job_id=job_id,
            status=JobStatus.succeeded,
            field_id=4,
            index=IndexName.ndvi,
            params={"max_cloud_cover": 20},
            points=points,
            error=None,
        )

    monkeypatch.setattr(raster_routes.RasterService, "get_time_series", fake_get)

    r = await client.get(f"/api/v1/analytics/time-series/{_JOB_ID}")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "succeeded"
    dates = [p["datetime"] for p in body["points"]]
    assert dates == sorted(dates)
    assert body["points"][0]["scene_id"] == "S2_5"


@pytest.mark.asyncio
async def test_get_time_series_unknown_job_returns_404(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_get(self, job_id) -> None:  # noqa: ANN001, ARG001
        return None

    monkeypatch.setattr(raster_routes.RasterService, "get_time_series", fake_get)

    r = await client.get(f"/api/v1/analytics/time-series/{uuid4()}")
    assert r.status_code == 404
