"""Route tests for the artifacts (data-cube) endpoints.

Monkeypatches ``ArtifactService`` so the routes run with no network/DB: asserts
202 + handle on create, the cached flag passes through, 404 for an unknown
artifact, and that the auth gate rejects an unauthenticated request.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from geogent_backend.api.v1.routes import artifacts as artifacts_routes
from geogent_backend.main import app
from geogent_backend.models.artifact import Artifact
from geogent_backend.schemas.artifact import ArtifactKind, ArtifactResponse
from geogent_backend.schemas.raster import JobStatus

_PAYLOAD = {
    "field_id": 4,
    "index": "ndvi",
    "start_date": "2025-04-01",
    "end_date": "2025-09-30",
}


@pytest.mark.asyncio
async def test_create_temporal_features_returns_202(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_create(self, recipe, background_tasks):  # noqa: ANN001, ANN202, ARG001
        assert recipe.field_id == 4
        row = Artifact(
            id="abc123",
            kind=ArtifactKind.temporal_features.value,
            recipe_hash="h",
            status=JobStatus.pending.value,
            recipe={},
        )
        return row, False

    monkeypatch.setattr(artifacts_routes.ArtifactService, "create_temporal_features", fake_create)

    r = await client.post("/api/v1/analytics/temporal-features", json=_PAYLOAD)
    assert r.status_code == 202
    body = r.json()
    assert body["artifact_id"] == "abc123"
    assert body["status"] == "pending"
    assert body["cached"] is False


@pytest.mark.asyncio
async def test_get_artifact_returns_summary(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_get(self, artifact_id):  # noqa: ANN001, ANN202, ARG001
        return ArtifactResponse(
            id=artifact_id,
            kind=ArtifactKind.temporal_features,
            status=JobStatus.succeeded,
            summary={"index": "ndvi", "n_scenes_used": 20},
            assets=[],
        )

    monkeypatch.setattr(artifacts_routes.ArtifactService, "get", fake_get)

    r = await client.get("/api/v1/analytics/artifacts/abc123")
    assert r.status_code == 200
    assert r.json()["summary"]["n_scenes_used"] == 20


@pytest.mark.asyncio
async def test_get_unknown_artifact_returns_404(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_get(self, artifact_id):  # noqa: ANN001, ANN202, ARG001
        return None

    monkeypatch.setattr(artifacts_routes.ArtifactService, "get", fake_get)

    r = await client.get("/api/v1/analytics/artifacts/nope")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_oversized_bbox_returns_422(client: AsyncClient) -> None:
    # A ~20°-wide bbox is far over the pixel cap; the guard rejects it before
    # any work is dispatched (no service monkeypatch / DB needed).
    r = await client.post(
        "/api/v1/analytics/temporal-features",
        json={
            "bbox": [-10.0, -10.0, 10.0, 10.0],
            "start_date": "2025-04-01",
            "end_date": "2025-09-30",
        },
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_requires_exactly_one_aoi(client: AsyncClient) -> None:
    # Neither field_id nor bbox nor geometry_wkt -> schema validation 422.
    r = await client.post(
        "/api/v1/analytics/temporal-features",
        json={"start_date": "2025-04-01", "end_date": "2025-09-30"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_temporal_features_requires_auth() -> None:
    # No get_current_user override here: the bearer guard must reject the call.
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/v1/analytics/temporal-features", json=_PAYLOAD)
    # Missing bearer → 401/403 (HTTPBearer auto_error), per the analytics auth gate.
    assert r.status_code in (401, 403)
