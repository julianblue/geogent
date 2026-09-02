"""Route + assembly tests for management zones (#65 M3).

The route tests monkeypatch the service (no network/DB). The assembly test
drives the *real* blocking builder with a stubbed cube read, so the wiring —
shared grid across indices, feature naming, summary shape, and the two assets a
zone map ships — is covered without touching GDAL or STAC.
"""

import json

import numpy as np
import pytest
from affine import Affine
from httpx import AsyncClient
from rasterio.crs import CRS

from geogent_backend.api.v1.routes import artifacts as artifacts_routes
from geogent_backend.geo import cube as cube_mod
from geogent_backend.models.artifact import Artifact
from geogent_backend.schemas.artifact import ArtifactKind, ManagementZonesRecipe
from geogent_backend.schemas.raster import JobStatus
from geogent_backend.services import artifact_service

_PAYLOAD = {
    "field_id": 4,
    "indices": ["ndvi"],
    "start_date": "2025-04-01",
    "end_date": "2025-09-30",
}

_GEOM = {
    "type": "Polygon",
    "coordinates": [[[13.9, 53.3], [13.91, 53.3], [13.91, 53.31], [13.9, 53.31], [13.9, 53.3]]],
}


@pytest.mark.asyncio
async def test_create_management_zones_returns_202(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_create(self, recipe, background_tasks):  # noqa: ANN001, ANN202, ARG001
        assert recipe.field_id == 4
        assert recipe.n_zones is None  # "auto" by default
        return (
            Artifact(
                id="zone123",
                kind=ArtifactKind.management_zones.value,
                recipe_hash="h",
                status=JobStatus.pending.value,
                recipe={},
            ),
            False,
        )

    monkeypatch.setattr(artifacts_routes.ArtifactService, "create_management_zones", fake_create)

    r = await client.post("/api/v1/analytics/management-zones", json=_PAYLOAD)

    assert r.status_code == 202
    assert r.json()["artifact_id"] == "zone123"
    assert r.json()["kind"] == "management_zones"


@pytest.mark.asyncio
async def test_management_zones_requires_exactly_one_aoi(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/analytics/management-zones",
        json={**_PAYLOAD, "bbox": [13.9, 53.3, 13.91, 53.31]},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_management_zones_rejects_an_index_the_sensor_lacks(client: AsyncClient) -> None:
    """Landsat has no red-edge band, so ndre must fail at the schema rather than
    halfway through a cube build."""
    r = await client.post(
        "/api/v1/analytics/management-zones",
        json={**_PAYLOAD, "collection": "landsat-c2-l2", "indices": ["ndre"]},
    )
    assert r.status_code == 422


def _fake_cube(values: np.ndarray, grid: cube_mod.CubeGrid) -> cube_mod.Cube:
    return cube_mod.Cube(
        values=values,
        dates=["2025-05-01", "2025-06-10", "2025-07-20"],
        grid=grid,
        index=cube_mod.IndexName.ndvi,
        collection_id="sentinel-2-l2a",
        n_scenes_found=3,
        n_scenes_used=3,
        n_scenes_failed=0,
        n_scenes_cloud_masked=3,
    )


def test_zone_build_assembles_summary_and_both_assets(monkeypatch: pytest.MonkeyPatch) -> None:
    """A two-halves field, two indices: one shared grid, four feature layers,
    a raster asset and a vector asset."""
    grid = cube_mod.CubeGrid(
        epsg=32633,
        crs=CRS.from_epsg(32633),
        transform=Affine(10.0, 0.0, 400_000.0, 0.0, -10.0, 5_900_000.0),
        width=40,
        height=40,
        polygon_mask=np.ones((40, 40), dtype=bool),
    )
    field = np.zeros((40, 40), dtype="float32")
    field[:, :20] = 0.30
    field[:, 20:] = 0.75
    stack = np.stack([field, field * 1.02, field * 0.98], axis=0)

    seen_grids: list[object] = []

    def fake_build_cube(geom, scenes, index, resolution_m, collection, grid=None):  # noqa: ANN001, ANN202, ARG001
        # Record what the builder passed in: the contract under test is that the
        # first call defines the grid and later ones are pinned to it.
        seen_grids.append(grid)
        return _fake_cube(stack.copy(), grid or grid_fixture)

    grid_fixture = grid
    monkeypatch.setattr(artifact_service.cube, "build_cube", fake_build_cube)

    recipe = ManagementZonesRecipe(
        field_id=4,
        indices=["ndvi", "ndmi"],
        start_date="2025-04-01",
        end_date="2025-09-30",
        n_zones=2,
    )
    summary, assets = artifact_service._build_zones(_GEOM, [{"id": "s1"}], recipe, 10.0)

    # The first index defines the grid; every later index is forced onto it.
    assert seen_grids[0] is None
    assert seen_grids[1] is grid

    assert summary["n_zones"] == 2
    assert summary["features"] == [
        "ndvi_productivity",
        "ndvi_stability",
        "ndmi_productivity",
        "ndmi_stability",
    ]
    assert set(summary["inputs"]) == {"ndvi", "ndmi"}
    assert summary["inputs"]["ndvi"]["n_scenes_cloud_masked"] == 3
    assert [z["zone"] for z in summary["zones"]] == [1, 2]
    assert summary["attribution"][0]["feature"].endswith("productivity")

    assert set(assets) == {"zones.tif", "zones.geojson"}
    assert assets["zones.tif"][:2] == b"II" or assets["zones.tif"][:2] == b"MM"  # TIFF magic
    geojson = json.loads(assets["zones.geojson"])
    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) == 2
    props = geojson["features"][0]["properties"]
    assert props["zone"] == 1
    assert props["area_ha"] > 0
    assert "ndvi_productivity" in props["features"]
