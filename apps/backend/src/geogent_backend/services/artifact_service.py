"""Orchestration for the artifacts (data-cube) endpoints.

Content-addresses each recipe (identical recipe -> reuse), dispatches the heavy
build to a background task with its own session, runs the blocking cube compute
on a worker thread, and writes the COG payload to the artifact store. The agent
only ever sees ``summary``; the UI resolves ``assets`` to render URLs. See
ADR 0002 and docs/design/m1-artifacts-data-model.md.
"""

from __future__ import annotations

import hashlib
import json
import logging
from uuid import uuid4

import anyio
from fastapi import BackgroundTasks
from geoalchemy2.shape import to_shape
from shapely.geometry import mapping, shape
from sqlalchemy.ext.asyncio import AsyncSession

from geogent_backend.config import get_settings
from geogent_backend.geo import cube, stac
from geogent_backend.models.artifact import Artifact
from geogent_backend.repositories.artifact_repo import ArtifactRepository
from geogent_backend.repositories.field_repo import FieldRepository
from geogent_backend.schemas.artifact import (
    ArtifactAsset,
    ArtifactKind,
    ArtifactResponse,
    TemporalFeaturesRecipe,
)
from geogent_backend.schemas.raster import JobStatus
from geogent_backend.services.raster_service import FieldNotFoundError
from geogent_backend.storage.artifact_store import ArtifactStore, get_artifact_store

logger = logging.getLogger(__name__)

# One single-band COG per field-memory layer; the key is also the asset role.
_FEATURE_ASSETS = ("productivity", "stability")
_ASSET_MEDIA_TYPE = "image/tiff; application=geotiff"


def recipe_hash(recipe: TemporalFeaturesRecipe) -> str:
    """Stable content hash of a recipe. Canonical (sorted keys), version-aware
    (``recipe_version`` busts the cache on a math change)."""
    payload = recipe.model_dump(mode="json")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _asset_url(artifact_id: str, key: str) -> str:
    return f"/api/v1/analytics/artifacts/{artifact_id}/assets/{key}"


def _to_response(row: Artifact) -> ArtifactResponse:
    assets = [ArtifactAsset(**a) for a in (row.assets or [])]
    return ArtifactResponse(
        id=row.id,
        kind=ArtifactKind(row.kind),
        status=JobStatus(row.status),
        summary=row.summary,
        assets=assets,
        error=row.error,
    )


class ArtifactService:
    def __init__(
        self,
        session: AsyncSession,
        owner: str | None,
        store: ArtifactStore | None = None,
    ) -> None:
        self._session = session
        # Normalize to a non-NULL sentinel: Postgres treats NULLs as distinct in
        # UNIQUE(owner, recipe_hash), so a NULL owner would defeat the
        # content-addressing dedup. "" means "unowned" (e.g. service-internal).
        self._owner = owner or ""
        self._repo = ArtifactRepository(session)
        self._store = store or get_artifact_store()
        self._settings = get_settings()

    async def create_temporal_features(
        self, recipe: TemporalFeaturesRecipe, background_tasks: BackgroundTasks
    ) -> tuple[Artifact, bool]:
        """Return the artifact for this recipe (building it if new). The bool is
        whether it was a cache hit."""
        # Fail fast on a missing field so the caller gets a 404, not a failed job.
        if await FieldRepository(self._session).get(recipe.field_id) is None:
            raise FieldNotFoundError(f"Field {recipe.field_id} not found")

        h = recipe_hash(recipe)
        existing = await self._repo.get_by_recipe(self._owner, h)
        if existing is not None:
            return existing, True

        artifact_id = uuid4().hex
        row = await self._repo.create_or_get(
            artifact_id,
            ArtifactKind.temporal_features.value,
            h,
            recipe.model_dump(mode="json"),
            self._owner,
        )
        if row.id == artifact_id:  # we won the insert race -> build it
            background_tasks.add_task(self._build_temporal_features, artifact_id, recipe)
            return row, False
        return row, True  # someone else created it first

    async def get(self, artifact_id: str) -> ArtifactResponse | None:
        row = await self._repo.get(artifact_id)
        if row is None or row.owner != self._owner:
            return None
        return _to_response(row)

    async def get_asset(self, artifact_id: str, key: str) -> bytes | None:
        row = await self._repo.get(artifact_id)
        if row is None or row.owner != self._owner:
            return None
        # Only serve keys this artifact actually declared — never read arbitrary
        # files under its directory, even for an owner who knows the id.
        declared = {a.get("key") for a in (row.assets or [])}
        if key not in declared:
            return None
        return await self._store.get(artifact_id, key)

    async def _build_temporal_features(
        self, artifact_id: str, recipe: TemporalFeaturesRecipe
    ) -> None:
        from geogent_backend.db.session import SessionLocal

        async with SessionLocal() as session:
            repo = ArtifactRepository(session)
            fields = FieldRepository(session)
            try:
                await repo.set_status(artifact_id, JobStatus.running.value)

                row = await fields.get(recipe.field_id)
                if row is None:
                    raise FieldNotFoundError(f"Field {recipe.field_id} not found")
                geom_4326 = mapping(to_shape(row.geometry))

                bbox = list(shape(geom_4326).bounds)
                max_scenes = min(recipe.max_scenes, self._settings.cube_max_scenes)
                scenes = await stac.search_scenes(
                    bbox,
                    recipe.start_date,
                    recipe.end_date,
                    max_cloud_cover=recipe.max_cloud_cover,
                    limit=max_scenes,
                )

                summary, cogs = await anyio.to_thread.run_sync(
                    cube.build_field_memory,
                    geom_4326,
                    scenes,
                    recipe.index,
                    self._settings.cube_resolution_m,
                )

                assets: list[dict] = []
                for role in _FEATURE_ASSETS:
                    key = f"{role}.tif"
                    await self._store.put(artifact_id, key, cogs[role])
                    assets.append(
                        ArtifactAsset(
                            role=role,
                            key=key,
                            url=_asset_url(artifact_id, key),
                            media_type=_ASSET_MEDIA_TYPE,
                            bands=[role],
                        ).model_dump()
                    )
                await repo.set_result(artifact_id, summary, assets)
            except FieldNotFoundError as exc:
                await repo.set_error(artifact_id, str(exc))
            except cube.CubeError as exc:
                await repo.set_error(artifact_id, str(exc))
            except Exception:
                logger.exception("Artifact build %s failed", artifact_id)
                await repo.set_error(artifact_id, "Artifact build failed.")
