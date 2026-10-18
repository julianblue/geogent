"""Route tests for the TESSERA embedding endpoints.

``EmbeddingService`` is monkeypatched so the routes run with no network/DB; the
store reader dependency is overridden (that is also the 503 seam).
"""

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from geogent_backend.api.v1.routes import embeddings as embeddings_routes
from geogent_backend.config import get_settings
from geogent_backend.geo import tessera
from geogent_backend.main import app
from geogent_backend.models.artifact import Artifact
from geogent_backend.schemas.artifact import ArtifactKind, ArtifactResponse
from geogent_backend.schemas.raster import JobStatus
from geogent_backend.services.artifact_service import AOITooLargeError
from geogent_backend.services.raster_service import FieldNotFoundError

_FIELD = {"field_id": 4, "start_year": 2020, "end_year": 2024}
_LAYER = {"year": 2024, "field_id": 4}


@pytest.fixture(autouse=True)
def fake_reader():  # noqa: ANN201
    """Every test gets a stub reader; the 503 tests replace this override."""
    app.dependency_overrides[embeddings_routes.get_tessera_reader] = lambda: object()
    yield
    app.dependency_overrides.pop(embeddings_routes.get_tessera_reader, None)


def _row(kind: ArtifactKind, status: JobStatus = JobStatus.pending) -> Artifact:
    return Artifact(id="abc123", kind=kind.value, recipe_hash="h", status=status.value, recipe={})


@pytest.mark.asyncio
async def test_create_field_embeddings_returns_202(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_create(self, recipe, background_tasks):  # noqa: ANN001, ANN202, ARG001
        assert recipe.field_id == 4 and recipe.years == [2020, 2021, 2022, 2023, 2024]
        assert recipe.centring == "aoi" and recipe.aoi_buffer_m == 1000 and recipe.dim == 128
        assert recipe.store_version == "v1.1" and recipe.recipe_version == 1
        return _row(ArtifactKind.field_embeddings), False

    monkeypatch.setattr(embeddings_routes.EmbeddingService, "create_field_embeddings", fake_create)
    r = await client.post("/api/v1/analytics/field-embeddings", json=_FIELD)
    assert r.status_code == 202
    assert r.json() == {
        "artifact_id": "abc123",
        "kind": "field_embeddings",
        "status": "pending",
        "cached": False,
    }


@pytest.mark.asyncio
async def test_create_embedding_layer_returns_202_and_cached_flag(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_create(self, recipe, background_tasks):  # noqa: ANN001, ANN202, ARG001
        assert recipe.year == 2024 and recipe.mode == "pca" and recipe.pad_m == 200
        return _row(ArtifactKind.embedding_layer, JobStatus.succeeded), True

    monkeypatch.setattr(embeddings_routes.EmbeddingService, "create_embedding_layer", fake_create)
    r = await client.post("/api/v1/analytics/embedding-layers", json=_LAYER)
    assert r.status_code == 202
    body = r.json()
    assert body["kind"] == "embedding_layer" and body["status"] == "succeeded"
    assert body["cached"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc,code",
    [
        (FieldNotFoundError("Field 4 not found"), 404),
        (AOITooLargeError("too big"), 422),
        (tessera.TesseraZoneError("two zones"), 422),
        (tessera.TesseraError("S3 down"), 502),
    ],
)
async def test_service_errors_map_to_http_codes(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, exc: Exception, code: int
) -> None:
    async def boom(self, recipe, background_tasks):  # noqa: ANN001, ANN202, ARG001
        raise exc

    monkeypatch.setattr(embeddings_routes.EmbeddingService, "create_field_embeddings", boom)
    monkeypatch.setattr(embeddings_routes.EmbeddingService, "create_embedding_layer", boom)
    for path, body in (("field-embeddings", _FIELD), ("embedding-layers", _LAYER)):
        r = await client.post(f"/api/v1/analytics/{path}", json=body)
        assert r.status_code == code
        assert str(exc) in r.json()["detail"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path,body",
    [
        ("field-embeddings", {**_FIELD, "end_year": 2019}),  # end < start
        ("field-embeddings", {**_FIELD, "start_year": 2016}),  # before the store
        ("field-embeddings", {**_FIELD, "start_year": 2017, "end_year": 2026}),  # beyond latest
        ("field-embeddings", {**_FIELD, "start_year": 2017, "end_year": 2025, "dim": 129}),
        ("field-embeddings", {**_FIELD, "start_year": 2010}),
        ("field-embeddings", {**_FIELD, "aoi_buffer_m": 6000}),
        ("field-embeddings", {**_FIELD, "centring": "global"}),
        ("field-embeddings", {"start_year": 2020, "end_year": 2021}),  # no field_id
        ("embedding-layers", {"year": 2024}),  # no AOI
        ("embedding-layers", {**_LAYER, "bbox": [16.0, 48.0, 16.1, 48.1]}),  # two AOIs
        ("embedding-layers", {"year": 2024, "bbox": [16.0, 48.0, 16.1, 48.1], "field_id": 1}),
        ("embedding-layers", {"year": 2026, "field_id": 1}),
        ("embedding-layers", {"year": 2016, "field_id": 1}),
        ("embedding-layers", {"year": 2024, "bbox": [16.1, 48.0, 16.0, 48.1]}),  # west > east
        ("embedding-layers", {"year": 2024, "geometry_wkt": "not wkt"}),
        ("embedding-layers", {**_LAYER, "mode": "umap"}),
        ("embedding-layers", {**_LAYER, "pad_m": 5000}),
    ],
)
async def test_invalid_recipes_are_422_before_any_work(
    client: AsyncClient, path: str, body: dict
) -> None:
    r = await client.post(f"/api/v1/analytics/{path}", json=body)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_span_over_max_years_is_422(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TESSERA_MAX_YEARS", "3")
    get_settings.cache_clear()
    try:
        r = await client.post("/api/v1/analytics/field-embeddings", json=_FIELD)  # 5 years
        assert r.status_code == 422 and "at most 3 years" in str(r.json())
    finally:
        monkeypatch.delenv("TESSERA_MAX_YEARS")
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_unavailable_reader_is_503(client: AsyncClient) -> None:
    def unavailable() -> None:
        raise HTTPException(503, detail="TESSERA support is not installed")

    app.dependency_overrides[embeddings_routes.get_tessera_reader] = unavailable
    for path, body in (("field-embeddings", _FIELD), ("embedding-layers", _LAYER)):
        r = await client.post(f"/api/v1/analytics/{path}", json=body)
        assert r.status_code == 503


def test_get_tessera_reader_is_503_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TESSERA_ENABLED", "false")
    get_settings.cache_clear()
    try:
        with pytest.raises(HTTPException) as e:
            embeddings_routes.get_tessera_reader()
        assert e.value.status_code == 503 and "disabled" in e.value.detail
    finally:
        monkeypatch.delenv("TESSERA_ENABLED")
        get_settings.cache_clear()


def test_get_tessera_reader_is_503_when_icechunk_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing() -> None:
        raise tessera.TesseraUnavailableError(
            "TESSERA support is not installed (missing: icechunk)"
        )

    monkeypatch.setattr(tessera, "ensure_available", missing)
    with pytest.raises(HTTPException) as e:
        embeddings_routes.get_tessera_reader()
    assert e.value.status_code == 503 and "icechunk" in e.value.detail


def test_get_tessera_reader_builds_a_cached_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(embeddings_routes, "_reader", None)
    first = embeddings_routes.get_tessera_reader()
    assert isinstance(first, tessera.IcechunkTesseraReader)  # lazy: no network on construct
    assert embeddings_routes.get_tessera_reader() is first


@pytest.mark.asyncio
async def test_new_kinds_serialise_through_the_generic_artifact_route(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from geogent_backend.api.v1.routes import artifacts as artifacts_routes

    async def fake_get(self, artifact_id):  # noqa: ANN001, ANN202, ARG001
        kind = (
            ArtifactKind.field_embeddings if artifact_id == "fe" else ArtifactKind.embedding_layer
        )
        return ArtifactResponse(id=artifact_id, kind=kind, status=JobStatus.succeeded, summary={})

    monkeypatch.setattr(artifacts_routes.ArtifactService, "get", fake_get)
    assert (await client.get("/api/v1/analytics/artifacts/fe")).json()["kind"] == "field_embeddings"
    assert (await client.get("/api/v1/analytics/artifacts/el")).json()["kind"] == "embedding_layer"


# --------------------------------------------------------------------------- auth boundary


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path,body",
    [("field-embeddings", _FIELD), ("embedding-layers", _LAYER)],
)
async def test_embedding_routes_require_auth(path: str, body: dict) -> None:
    # No get_current_user override: the bearer guard must reject before the reader
    # dependency or the service is touched (even with TESSERA unavailable).
    app.dependency_overrides.pop(embeddings_routes.get_tessera_reader, None)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        missing = await c.post(f"/api/v1/analytics/{path}", json=body)
        invalid = await c.post(
            f"/api/v1/analytics/{path}", json=body, headers={"Authorization": "Bearer nope"}
        )
    assert missing.status_code in (401, 403)  # HTTPBearer auto_error
    assert invalid.status_code == 401
