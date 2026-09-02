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
from geogent_backend.geo import collections, cube, reducers, stac, zones
from geogent_backend.geo.reducers import ReducerName
from geogent_backend.models.artifact import Artifact
from geogent_backend.repositories.artifact_repo import ArtifactRepository
from geogent_backend.repositories.field_repo import FieldRepository
from geogent_backend.schemas.artifact import (
    ArtifactAsset,
    ArtifactKind,
    ArtifactResponse,
    ManagementZonesRecipe,
    TemporalFeaturesRecipe,
)
from geogent_backend.schemas.raster import JobStatus
from geogent_backend.services.raster_service import FieldNotFoundError
from geogent_backend.storage.artifact_store import ArtifactStore, get_artifact_store

logger = logging.getLogger(__name__)

_ASSET_MEDIA_TYPE = "image/tiff; application=geotiff"
_GEOJSON_MEDIA_TYPE = "application/geo+json"


class AOITooLargeError(Exception):
    """The requested AOI would exceed the in-process pixel budget (-> 422)."""


async def _resolve_geometry(
    session: AsyncSession, recipe: TemporalFeaturesRecipe | ManagementZonesRecipe
) -> dict:
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


def recipe_hash(recipe: TemporalFeaturesRecipe | ManagementZonesRecipe) -> str:
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


def _build_zones(
    geom_4326: dict,
    scenes: list[dict],
    recipe: ManagementZonesRecipe,
    resolution_m: float,
) -> tuple[dict, dict[str, bytes]]:
    """Blocking zone delineation: one cube per index, then cluster the stack.

    Every cube after the first is forced onto the FIRST cube's grid, so the
    feature layers are co-registered by construction rather than by luck — that
    alignment is what makes stacking indices into one clustering input valid.
    """
    coll = collections.get_spec(recipe.collection)
    features: list[zones.FeatureLayer] = []
    provenance: dict[str, dict] = {}
    grid = None
    observed = None

    reducer = reducers.get_spec(ReducerName.field_memory)
    for index in recipe.indices:
        built = cube.build_cube(geom_4326, scenes, index, resolution_m, coll, grid=grid)
        grid = built.grid
        outputs = reducer.reduce(built.values, cube.decimal_years(built.dates), {})
        for name, layer in outputs.items():
            features.append(zones.FeatureLayer(name=f"{index.value}_{name}", values=layer))
        provenance[index.value] = cube.cube_provenance(built, resolution_m)
        seen = built.valid_obs_per_pixel > 0
        observed = seen if observed is None else (observed & seen)

    assert grid is not None and observed is not None
    result, polygons = zones.delineate(
        features,
        grid.polygon_mask & observed,
        grid.transform,
        grid.crs,
        n_zones=recipe.n_zones,
    )

    summary = {
        "n_zones": result.n_zones,
        "zones": result.zones,
        "attribution": result.attribution,
        "zone_count_selection": result.selection,
        "clustered_pixels": result.n_pixels,
        "features": [f.name for f in features],
        "inputs": provenance,
    }
    assets = {
        "zones.tif": cube.write_single_band_cog(result.labels, grid.crs, grid.transform, "zones"),
        "zones.geojson": json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": polygons[z["zone"]],
                        "properties": {k: v for k, v in z.items() if k != "zone"}
                        | {"zone": z["zone"]},
                    }
                    for z in result.zones
                    if z["zone"] in polygons
                ],
            }
        ).encode("utf-8"),
    }
    return summary, assets


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

    async def _create(
        self,
        kind: ArtifactKind,
        recipe: TemporalFeaturesRecipe | ManagementZonesRecipe,
        build_task,
        background_tasks: BackgroundTasks,
    ) -> tuple[Artifact, bool]:
        """Content-address a recipe and dispatch its build if it is new.

        Shared by every artifact kind: resolve the AOI up front so a missing
        field is a 404 (not a failed job) and an oversized AOI a 422 before any
        work is dispatched; then dedup on the recipe hash. The bool is whether
        this was a cache hit.
        """
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
            artifact_id, kind.value, h, recipe.model_dump(mode="json"), self._owner
        )
        if row.id == artifact_id:  # we won the insert race -> build it
            background_tasks.add_task(build_task, artifact_id, recipe)
            return row, False
        return row, True  # someone else created it first

    async def create_temporal_features(
        self, recipe: TemporalFeaturesRecipe, background_tasks: BackgroundTasks
    ) -> tuple[Artifact, bool]:
        return await self._create(
            ArtifactKind.temporal_features,
            recipe,
            self._build_temporal_features,
            background_tasks,
        )

    async def create_management_zones(
        self, recipe: ManagementZonesRecipe, background_tasks: BackgroundTasks
    ) -> tuple[Artifact, bool]:
        return await self._create(
            ArtifactKind.management_zones,
            recipe,
            self._build_management_zones,
            background_tasks,
        )

    async def get(self, artifact_id: str) -> ArtifactResponse | None:
        row = await self._repo.get(artifact_id)
        if row is None or row.owner != self._owner:
            return None
        return _to_response(row)

    async def get_asset(self, artifact_id: str, key: str) -> tuple[bytes, str] | None:
        """Bytes plus the asset's declared media type (rasters and GeoJSON differ)."""
        row = await self._repo.get(artifact_id)
        if row is None or row.owner != self._owner:
            return None
        # Only serve keys this artifact actually declared — never read arbitrary
        # files under its directory, even for an owner who knows the id.
        declared = {a.get("key"): a for a in (row.assets or [])}
        if key not in declared:
            return None
        data = await self._store.get(artifact_id, key)
        if data is None:
            return None
        return data, str(declared[key].get("media_type") or _ASSET_MEDIA_TYPE)

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

    async def _build_management_zones(
        self, artifact_id: str, recipe: ManagementZonesRecipe
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
                # One scene search shared by every index — same AOI, same window,
                # so the cubes see the same acquisitions and stay comparable.
                scenes = await stac.search_scenes(
                    bbox,
                    recipe.start_date,
                    recipe.end_date,
                    max_cloud_cover=recipe.max_cloud_cover,
                    limit=max_scenes,
                    collection=coll.stac_id,
                    cloud_field=coll.cloud_field,
                )

                summary, payloads = await anyio.to_thread.run_sync(
                    _build_zones,
                    geom_4326,
                    scenes,
                    recipe,
                    self._settings.cube_resolution_m,
                )

                assets: list[dict] = []
                for key, data in payloads.items():
                    await self._store.put(artifact_id, key, data)
                    is_raster = key.endswith(".tif")
                    assets.append(
                        ArtifactAsset(
                            # The raster is what the map renders (discrete
                            # "zones" ramp); the GeoJSON is the exportable
                            # boundary set the VRA path (M4) will build on.
                            role="zones" if is_raster else "zones_geojson",
                            key=key,
                            url=_asset_url(artifact_id, key),
                            media_type=_ASSET_MEDIA_TYPE if is_raster else _GEOJSON_MEDIA_TYPE,
                            colormap="zones",
                            label="Management zones",
                            bands=["zones"] if is_raster else [],
                        ).model_dump()
                    )
                await repo.set_result(artifact_id, summary, assets)
            except FieldNotFoundError as exc:
                await repo.set_error(artifact_id, str(exc))
            except (cube.CubeError, zones.ZoneError) as exc:
                await repo.set_error(artifact_id, str(exc))
            except Exception:
                logger.exception("Zone build %s failed", artifact_id)
                await repo.set_error(artifact_id, "Management-zone build failed.")
