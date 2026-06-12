"""Route-level tests for /api/v1/fields/*.

Monkeypatches FieldService so the route tests don't need a running PostGIS
(the migrations smoke-test job covers schema/SQL correctness against a real DB).
The geometry round-trip is exercised directly against the ORM model with a real
fixture polygon, no DB required.
"""

from datetime import UTC, datetime

import pytest
from geoalchemy2.shape import from_shape
from httpx import AsyncClient
from shapely.geometry import shape

from geogent_backend.api.v1.routes import fields as fields_routes
from geogent_backend.models.field import Field
from geogent_backend.schemas.field import FieldRead
from geogent_backend.services.field_service import field_to_read

# A real ~5 ha rectangular field near Ames, Iowa (lon/lat, SRID 4326).
FIXTURE_POLYGON = {
    "type": "Polygon",
    "coordinates": [
        [
            [-93.650, 42.020],
            [-93.647, 42.020],
            [-93.647, 42.022],
            [-93.650, 42.022],
            [-93.650, 42.020],
        ]
    ],
}


def _read(
    field_id: int = 1,
    name: str = "North Forty",
    crop: str | None = "corn",
    season: str | None = "2026",
) -> FieldRead:
    return FieldRead(
        id=field_id,
        name=name,
        crop=crop,
        season=season,
        geometry=FIXTURE_POLYGON,
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_create_field_returns_201(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_create(self, payload) -> FieldRead:  # noqa: ANN001, ARG001
        assert payload.name == "North Forty"
        assert payload.crop == "corn"
        assert payload.geometry.type == "Polygon"
        return _read()

    monkeypatch.setattr(fields_routes.FieldService, "create_field", fake_create)

    r = await client.post(
        "/api/v1/fields",
        json={
            "name": "North Forty",
            "crop": "corn",
            "season": "2026",
            "geometry": FIXTURE_POLYGON,
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["id"] == 1
    assert body["crop"] == "corn"
    assert body["geometry"]["type"] == "Polygon"


@pytest.mark.asyncio
async def test_create_field_rejects_non_polygon(client: AsyncClient) -> None:
    """A point is not a field; schema validation rejects it before the DB."""
    r = await client.post(
        "/api/v1/fields",
        json={"name": "bad", "geometry": {"type": "Point", "coordinates": [-93.65, 42.02]}},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_list_fields(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_list(self) -> list[FieldRead]:  # noqa: ANN001, ARG001
        return [_read()]

    monkeypatch.setattr(fields_routes.FieldService, "list_fields", fake_list)

    r = await client.get("/api/v1/fields")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["name"] == "North Forty"


@pytest.mark.asyncio
async def test_get_field_found(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get(self, field_id: int) -> FieldRead:  # noqa: ANN001, ARG001
        return _read(field_id=field_id)

    monkeypatch.setattr(fields_routes.FieldService, "get_field", fake_get)

    r = await client.get("/api/v1/fields/7")
    assert r.status_code == 200
    assert r.json()["id"] == 7


@pytest.mark.asyncio
async def test_get_field_missing_returns_404(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_get(self, field_id: int) -> None:  # noqa: ANN001, ARG001
        return None

    monkeypatch.setattr(fields_routes.FieldService, "get_field", fake_get)

    r = await client.get("/api/v1/fields/999")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_update_field(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_update(self, field_id: int, payload) -> FieldRead:  # noqa: ANN001, ARG001
        assert payload.crop == "soybeans"
        return _read(field_id=field_id, crop="soybeans")

    monkeypatch.setattr(fields_routes.FieldService, "update_field", fake_update)

    r = await client.patch("/api/v1/fields/3", json={"crop": "soybeans"})
    assert r.status_code == 200
    assert r.json()["crop"] == "soybeans"


@pytest.mark.asyncio
async def test_update_field_missing_returns_404(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_update(self, field_id: int, payload) -> None:  # noqa: ANN001, ARG001
        return None

    monkeypatch.setattr(fields_routes.FieldService, "update_field", fake_update)

    r = await client.patch("/api/v1/fields/999", json={"crop": "soybeans"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_field(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_delete(self, field_id: int) -> bool:  # noqa: ANN001, ARG001
        return True

    monkeypatch.setattr(fields_routes.FieldService, "delete_field", fake_delete)

    r = await client.delete("/api/v1/fields/1")
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_delete_field_missing_returns_404(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_delete(self, field_id: int) -> bool:  # noqa: ANN001, ARG001
        return False

    monkeypatch.setattr(fields_routes.FieldService, "delete_field", fake_delete)

    r = await client.delete("/api/v1/fields/999")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_fields_in_bbox(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_bbox(
        self, min_lon: float, min_lat: float, max_lon: float, max_lat: float, crop=None, limit=None
    ) -> list[FieldRead]:  # noqa: ANN001, ARG001
        assert (min_lon, min_lat, max_lon, max_lat) == (-94.0, 41.0, -93.0, 43.0)
        assert crop is None and limit is None
        return [_read()]

    monkeypatch.setattr(fields_routes.FieldService, "fields_in_bbox", fake_bbox)

    r = await client.get(
        "/api/v1/fields/in-bbox",
        params={"min_lon": -94.0, "min_lat": 41.0, "max_lon": -93.0, "max_lat": 43.0},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["geometry"]["type"] == "Polygon"


@pytest.mark.asyncio
async def test_fields_in_bbox_rejects_out_of_range_lat(client: AsyncClient) -> None:
    r = await client.get(
        "/api/v1/fields/in-bbox",
        params={"min_lon": -94.0, "min_lat": -100.0, "max_lon": -93.0, "max_lat": 43.0},
    )
    assert r.status_code == 422


def test_field_to_read_round_trips_fixture_polygon() -> None:
    """ORM WKB geometry → GeoJSON conversion preserves the real fixture polygon."""
    geom = shape(FIXTURE_POLYGON)
    row = Field(
        id=1,
        name="North Forty",
        crop="corn",
        season="2026",
        geometry=from_shape(geom, srid=4326),
        created_at=datetime.now(UTC),
    )
    read = field_to_read(row)
    assert read.geometry.type == "Polygon"
    assert shape(read.geometry.model_dump()).equals(geom)


@pytest.mark.asyncio
async def test_fields_in_bbox_forwards_crop_and_limit(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict = {}

    async def fake_bbox(self, min_lon, min_lat, max_lon, max_lat, crop=None, limit=None):  # noqa: ANN001, ARG001
        captured.update(crop=crop, limit=limit)
        return [_read(crop="winter_common_soft_wheat")]

    monkeypatch.setattr(fields_routes.FieldService, "fields_in_bbox", fake_bbox)

    r = await client.get(
        "/api/v1/fields/in-bbox",
        params={
            "min_lon": 13.75,
            "min_lat": 53.20,
            "max_lon": 14.05,
            "max_lat": 53.40,
            "crop": "wheat",
            "limit": 10,
        },
    )
    assert r.status_code == 200
    assert captured == {"crop": "wheat", "limit": 10}
    assert r.json()[0]["crop"] == "winter_common_soft_wheat"


@pytest.mark.asyncio
async def test_crop_stats(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from geogent_backend.schemas.field import CropStat

    async def fake_stats(self, min_lon, min_lat, max_lon, max_lat):  # noqa: ANN001, ARG001
        return [
            CropStat(crop="winter_common_soft_wheat", parcels=81, total_area_ha=1843.5),
            CropStat(crop="winter_barley", parcels=48, total_area_ha=588.1),
        ]

    monkeypatch.setattr(fields_routes.FieldService, "crop_stats", fake_stats)

    r = await client.get(
        "/api/v1/fields/crop-stats",
        params={"min_lon": 13.75, "min_lat": 53.20, "max_lon": 14.05, "max_lat": 53.40},
    )
    assert r.status_code == 200
    body = r.json()
    assert body[0] == {"crop": "winter_common_soft_wheat", "parcels": 81, "total_area_ha": 1843.5}
    assert len(body) == 2


@pytest.mark.asyncio
async def test_crop_stats_rejects_bad_bbox_params(client: AsyncClient) -> None:
    r = await client.get(
        "/api/v1/fields/crop-stats",
        params={"min_lon": 13.75, "min_lat": -95.0, "max_lon": 14.05, "max_lat": 53.40},
    )
    assert r.status_code == 422
