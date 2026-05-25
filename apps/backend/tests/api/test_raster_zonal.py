"""Route test for POST /api/v1/analytics/zonal-stats.

Monkeypatches ``RasterService.zonal_stats`` (mirroring test_fields.py's
FieldService monkeypatch) so the route runs with no network/DB. We assert the
response schema and that the request fields reach the service.
"""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from geogent_backend.api.v1.routes import raster as raster_routes
from geogent_backend.schemas.raster import (
    Histogram,
    IndexName,
    SceneRef,
    ZonalStats,
    ZonalStatsResponse,
)


def _canned_response(field_id: int = 1) -> ZonalStatsResponse:
    return ZonalStatsResponse(
        field_id=field_id,
        index=IndexName.ndvi,
        scene=SceneRef(
            id="S2A_15TVG_20260520_0_L2A",
            datetime=datetime(2026, 5, 20, 17, 0, tzinfo=UTC),
            cloud_cover=3.2,
            epsg=32615,
        ),
        stats=ZonalStats(
            mean=0.42, min=-0.03, max=0.86, std=0.11, valid_pixels=9910, nodata_pixels=12
        ),
        histogram=Histogram(bin_edges=[-0.1, 0.0, 0.1], counts=[5, 9905]),
        cached=False,
    )


@pytest.mark.asyncio
async def test_zonal_stats_returns_200(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_zonal(self, req) -> ZonalStatsResponse:  # noqa: ANN001, ARG001
        assert req.field_id == 7
        assert req.index == IndexName.ndvi
        return _canned_response(field_id=req.field_id)

    monkeypatch.setattr(raster_routes.RasterService, "zonal_stats", fake_zonal)

    r = await client.post(
        "/api/v1/analytics/zonal-stats",
        json={"field_id": 7, "index": "ndvi"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["field_id"] == 7
    assert body["index"] == "ndvi"
    assert body["scene"]["id"] == "S2A_15TVG_20260520_0_L2A"
    assert body["stats"]["mean"] == 0.42
    assert body["histogram"]["counts"] == [5, 9905]
    assert body["cached"] is False


@pytest.mark.asyncio
async def test_zonal_stats_field_not_found_returns_404(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from geogent_backend.services.raster_service import FieldNotFoundError

    async def fake_zonal(self, req) -> ZonalStatsResponse:  # noqa: ANN001, ARG001
        raise FieldNotFoundError("Field 999 not found")

    monkeypatch.setattr(raster_routes.RasterService, "zonal_stats", fake_zonal)

    r = await client.post("/api/v1/analytics/zonal-stats", json={"field_id": 999})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_zonal_stats_rejects_bad_histogram_bins(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/analytics/zonal-stats",
        json={"field_id": 1, "histogram_bins": 0},
    )
    assert r.status_code == 422
