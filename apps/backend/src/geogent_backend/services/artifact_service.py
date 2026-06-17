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
import math
from uuid import uuid4

import anyio
from fastapi import BackgroundTasks
from geoalchemy2.shape import to_shape
from shapely import wkt
from shapely.geometry import box, mapping, shape
from sqlalchemy.ext.asyncio import AsyncSession

from geogent_backend.config import get_settings
from geogent_backend.geo import collections, cube, reducers, stac
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

_ASSET_MEDIA_TYPE = "image/tiff; application=geotiff"


class AOITooLargeError(Exception):
    """The requested AOI would exceed the in-process pixel budget (-> 422)."""


async def _resolve_geometry(session: AsyncSession, recipe: TemporalFeaturesRecipe) -> dict:
    """Resolve the recipe's AOI to a WGS84 GeoJSON geometry."""
    if recipe.field_id is not None:
        row = await FieldRepository(session).get(recipe.field_id)
        if row is None:
            raise FieldNotFoundError(f"Field {recipe.field_id} not found")
        return mapping(to_shape(row.geometry))
    if recipe.geometry_wkt is not None:
        return mapping(wkt.loads(recipe.geometry_wkt))
    return mapping(box(*recipe.bbox))  # validator guarantees one AOI is set


def _estimate_pixels(geom_4326: dict, resolution_m: float) -> int:
    """Rough pixel count of the AOI's grid at ``resolution_m`` (lat-corrected
    degrees → metres). Approximate — only used as a cost guard, not for sizing."""
    minx, miny, maxx, maxy = shape(geom_4326).bounds
    midlat = math.radians((miny + maxy) / 2.0)
    width_m = (maxx - minx) * 111_320.0 * max(math.cos(midlat), 0.01)
    height_m = (maxy - miny) * 110_540.0
    return math.ceil(width_m / resolution_m) * math.ceil(height_m / resolution_m)


def recipe_hash(recipe: TemporalFeaturesRecipe) -> str:
    """Stable content hash of a recipe. Canonical (sorted keys), version-aware
    (``recipe_version`` busts the cache on a math change)."""
    payload = recipe.model_dump(mode="json")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _asset_url(artifact_id: str, key: str) -> str:
    return f"/api/v1/analytics/artifacts/{artifact_id}/assets/{key}"


def _build(
    geom_4326: dict, scenes: list[dict], recipe: TemporalFeaturesRecipe, resolution_m: float
) -> tuple[dict, dict[str, bytes]]:
    """Blocking cube build + reduction; runs on a worker thread."""
    return cube.build_reduction(
        geom_4326,
        scenes,
        recipe.index,
        recipe.reducer,
        resolution_m,
        recipe.reducer_params,
        collection=collections.get_spec(recipe.collection),
    )


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
        # Resolve the AOI up front so a missing field is a 404 (not a failed job)
        # and an oversized AOI is a 422 before any work is dispatched.
        geom_4326 = await _resolve_geometry(self._session, recipe)
        pixels = _estimate_pixels(geom_4326, self._settings.cube_resolution_m)
        if pixels > self._settings.cube_max_pixels:
            raise AOITooLargeError(
                f"AOI is ~{pixels:,} px at {self._settings.cube_resolution_m:g} m "
                f"(limit {self._settings.cube_max_pixels:,}); use a smaller area."
            )

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
            try:
                await repo.set_status(artifact_id, JobStatus.running.value)

                geom_4326 = await _resolve_geometry(session, recipe)
                bbox = list(shape(geom_4326).bounds)
                max_scenes = min(recipe.max_scenes, self._settings.cube_max_scenes)
                coll = collections.get_spec(recipe.collection)
                scenes = await stac.search_scenes(
                    bbox,
                    recipe.start_date,
                    recipe.end_date,
                    max_cloud_cover=recipe.max_cloud_cover,
                    limit=max_scenes,
                    collection=coll.stac_id,
                    cloud_field=coll.cloud_field,
                )

                summary, cogs = await anyio.to_thread.run_sync(
                    _build,
                    geom_4326,
                    scenes,
                    recipe,
                    self._settings.cube_resolution_m,
                )

                outputs = {o.name: o for o in reducers.get_spec(recipe.reducer).outputs}
                assets: list[dict] = []
                for name, data in cogs.items():
                    key = f"{name}.tif"
                    await self._store.put(artifact_id, key, data)
                    out = outputs[name]
                    assets.append(
                        ArtifactAsset(
                            role=name,
                            key=key,
                            url=_asset_url(artifact_id, key),
                            media_type=_ASSET_MEDIA_TYPE,
                            colormap=out.colormap,
                            label=out.label,
                            bands=[name],
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
