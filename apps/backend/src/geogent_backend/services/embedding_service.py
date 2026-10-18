"""Orchestration for the TESSERA embedding artifacts (ADR 0003).

Mirrors the field-memory flow in :mod:`artifact_service` — content-address the
recipe, dispatch the heavy build to a background task with its own session, run
the blocking store read + maths on a worker thread, write the payload to the
artifact store — with three differences:

- a cached row that **failed** is reset and re-dispatched (a transient store
  error must not poison the recipe hash forever);
- store reads run on a dedicated bounded thread pool (``fail_after`` cannot cancel a
  thread, so the pool's worker count — held until the read really ends — is what
  caps in-flight reads, however many callers have timed out); and
- the two builders (:func:`build_field_embeddings`, :func:`build_embedding_layer`)
  are plain sync functions over a :class:`TesseraReader`, so they are tested with
  a fake reader and no DB, network or event loop.
"""

from __future__ import annotations

import asyncio
import io
import logging
import math
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import anyio
import numpy as np
from fastapi import BackgroundTasks
from geoalchemy2.shape import to_shape
from rasterio.crs import CRS
from rasterio.warp import transform_bounds, transform_geom
from shapely import wkt
from shapely.geometry import mapping, shape
from sqlalchemy.ext.asyncio import AsyncSession

from geogent_backend.config import Settings, get_settings
from geogent_backend.geo import cube, tessera
from geogent_backend.geo import embeddings as emb
from geogent_backend.geo.tessera import BBox, EmbeddingWindow, TesseraReader
from geogent_backend.models.artifact import Artifact
from geogent_backend.repositories.artifact_repo import ArtifactRepository
from geogent_backend.repositories.field_repo import FieldRepository
from geogent_backend.schemas.artifact import ArtifactAsset, ArtifactKind
from geogent_backend.schemas.embedding import (
    CentringSummary,
    EmbeddingLayerRecipe,
    EmbeddingLayerSummary,
    FieldEmbeddingsRecipe,
    FieldEmbeddingsSummary,
    FieldYearSummary,
    GridSummary,
    MaskingSummary,
    RotationScreen,
    YoYSummary,
)
from geogent_backend.schemas.raster import JobStatus
from geogent_backend.services.artifact_service import (
    _ASSET_MEDIA_TYPE,
    AOITooLargeError,
    _asset_url,
    recipe_hash,
)
from geogent_backend.services.raster_service import FieldNotFoundError
from geogent_backend.storage.artifact_store import ArtifactStore, get_artifact_store

logger = logging.getLogger(__name__)

PAYLOAD_KEY = "field_embeddings.npz"
LAYER_KEY = "pca_rgb.tif"
# Below this field size the year-over-year signal does not separate rotation.
ROTATION_MIN_AREA_HA = 1.0
_STRETCH = "p2–p98 per component; valid 1..255; 0=nodata"

_read_pool: ThreadPoolExecutor | None = None


def _read_executor(workers: int) -> ThreadPoolExecutor:
    """Process-wide pool whose size is the cap on concurrent store reads.

    A worker is occupied until its read returns, so a caller that gave up (deadline)
    does not free a slot while its thread is still running; further reads queue
    behind it instead of piling more threads onto a stuck store."""
    global _read_pool
    if _read_pool is None:
        _read_pool = ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="tessera")
    return _read_pool


def _finite(x: float) -> float | None:
    return float(x) if math.isfinite(x) else None


# --------------------------------------------------------------------------- builders


def _utm_geometry(geom_4326: dict, crs: CRS):  # noqa: ANN202 - shapely geometry
    return shape(transform_geom("EPSG:4326", crs, geom_4326))


def _window_bbox_wgs84(window: EmbeddingWindow) -> BBox:
    _, h, w = window.emb.shape[1:]  # (band, y, x)
    x0, y0 = window.transform * (0, h)
    x1, y1 = window.transform * (w, 0)
    west, south, east, north = transform_bounds(window.crs, "EPSG:4326", x0, y0, x1, y1, 21)
    return (west, south, east, north)


def _grid_summary(window: EmbeddingWindow, with_size: bool = False) -> GridSummary:
    _, _, h, w = window.emb.shape
    return GridSummary(
        epsg=window.crs.to_epsg(),
        resolution_m=abs(window.transform.a),
        width=w if with_size else None,
        height=h if with_size else None,
    )


def field_read_bbox(geom_4326: dict, recipe: FieldEmbeddingsRecipe) -> BBox:
    """The window read for a field: its bbox plus the centring buffer."""
    bounds = shape(geom_4326).bounds
    return tessera.expand_bbox_m(bounds, recipe.aoi_buffer_m if recipe.centring == "aoi" else 0)


def layer_bbox(geom_4326: dict | None, recipe: EmbeddingLayerRecipe) -> BBox:
    """The window of an embedding layer. ``geom_4326`` is the resolved field polygon
    when the recipe is field-based (padded by ``pad_m``), else ignored."""
    if recipe.bbox is not None:
        return recipe.bbox
    if recipe.geometry_wkt is not None:
        return tessera.expand_bbox_m(wkt.loads(recipe.geometry_wkt).bounds, 0)
    assert geom_4326 is not None  # field_id recipes always resolve a polygon
    return tessera.expand_bbox_m(shape(geom_4326).bounds, recipe.pad_m)


def _check_years_available(reader: TesseraReader, bbox: BBox, years: list[int]) -> None:
    group = tessera.bbox_zone_group(bbox)
    missing = sorted(set(years) - reader.years_complete(group))
    if missing:
        raise tessera.TesseraError(f"years {missing} are not yet complete in TESSERA zone {group}")


def build_field_embeddings(
    reader: TesseraReader, geom_4326: dict, recipe: FieldEmbeddingsRecipe
) -> tuple[dict, bytes]:
    """Blocking: read the years, mask the field, reduce to per-year stats + YoY.

    Returns ``(summary_dict, npz_bytes)``. The summary is the compact thing the
    agent sees; the npz holds the vectors (years, mean, std, pixel_count,
    aoi_year_mean, centred_mean)."""
    bbox = field_read_bbox(geom_4326, recipe)
    years = recipe.years
    _check_years_available(reader, bbox, years)
    window = reader.read_window(bbox, years, recipe.dim)

    geom_proj = _utm_geometry(geom_4326, window.crs)
    area_ha = geom_proj.area / 10_000.0
    _, _, h, w = window.emb.shape
    mask, buffered = emb.field_mask(geom_proj, (h, w), window.transform)

    stats = [emb.year_stats(window.emb[i], mask) for i in range(len(years))]
    # the window's own band count, not recipe.dim: a store may expose fewer bands
    n_years, dim = len(years), window.emb.shape[1]
    offsets = np.zeros((n_years, dim), dtype=np.float64)
    aoi_pixels: dict[str, int] = {}
    for i, year in enumerate(years):
        mean_i, n_i = emb.window_mean(window.emb[i])
        aoi_pixels[str(year)] = n_i
        if recipe.centring == "aoi" and n_i:
            offsets[i] = mean_i

    # A year with no usable pixels (or no AOI pixels to centre on) has no
    # trustworthy mean, so it drops out of the pairs rather than reading as 0.
    yoy: list[YoYSummary] = []
    for i in range(n_years - 1):
        a, b = stats[i], stats[i + 1]
        if not (a.usable and b.usable):
            continue
        if recipe.centring == "aoi" and not (
            aoi_pixels[str(years[i])] and aoi_pixels[str(years[i + 1])]
        ):
            continue
        centred, raw = emb.yoy_distance(a.mean, b.mean, offsets[i], offsets[i + 1])
        if math.isfinite(centred) and math.isfinite(raw):
            yoy.append(
                YoYSummary(
                    from_year=years[i],
                    to_year=years[i + 1],
                    cosine_distance_centred=centred,
                    cosine_distance_raw=raw,
                )
            )

    per_year = [
        FieldYearSummary(
            year=year,
            pixel_count=s.pixel_count,
            masked_fraction=s.masked_fraction,
            mean_norm=_finite(float(np.linalg.norm(s.mean))),
            mean_std=_finite(float(np.mean(s.std))),
            heterogeneity=_finite(s.heterogeneity),
            usable=s.usable,
        )
        for year, s in zip(years, stats, strict=True)
    ]
    summary = FieldEmbeddingsSummary(
        field_id=recipe.field_id,
        area_ha=round(area_ha, 3),
        years=years,
        dim=dim,
        store_version=recipe.store_version,
        grid=_grid_summary(window),
        assumed_window=tessera.ASSUMED_WINDOW,
        masking=MaskingSummary(inward_buffer_m=emb.INWARD_BUFFER_M, buffered=buffered),
        per_year=per_year,
        yoy=yoy,
        centring=CentringSummary(
            mode=recipe.centring, aoi_buffer_m=recipe.aoi_buffer_m, aoi_pixels_by_year=aoi_pixels
        ),
        rotation_screen=RotationScreen(
            valid=area_ha >= ROTATION_MIN_AREA_HA, min_area_ha=ROTATION_MIN_AREA_HA
        ),
        payload_key=PAYLOAD_KEY,
    )

    means = np.stack([s.mean for s in stats])
    buf = io.BytesIO()
    np.savez_compressed(
        buf,
        years=np.array(years, dtype=np.int32),
        mean=means.astype(np.float32),
        std=np.stack([s.std for s in stats]).astype(np.float32),
        pixel_count=np.array([s.pixel_count for s in stats], dtype=np.int32),
        aoi_year_mean=offsets.astype(np.float32),
        centred_mean=(means - offsets).astype(np.float32),
    )
    return summary.model_dump(mode="json"), buf.getvalue()


def build_embedding_layer(
    reader: TesseraReader, bbox: BBox, recipe: EmbeddingLayerRecipe
) -> tuple[dict, bytes]:
    """Blocking: read one year's window and render its PCA(3) false-colour COG."""
    _check_years_available(reader, bbox, [recipe.year])
    window = reader.read_window(bbox, [recipe.year], recipe.dim)
    rgb, valid, ratio = emb.pca_rgb(window.emb[0])
    if not valid.any():
        raise tessera.TesseraNoDataError(
            "No TESSERA embeddings in this window (outside coverage, water, or too few "
            "satellite observations)."
        )
    cog = cube.write_rgb_cog(rgb, window.crs, window.transform)
    summary = EmbeddingLayerSummary(
        mode=recipe.mode,
        year=recipe.year,
        dim=window.emb.shape[1],
        explained_variance_ratio=[float(r) for r in ratio],
        valid_fraction=float(valid.mean()),
        grid=_grid_summary(window, with_size=True),
        bbox_wgs84=_window_bbox_wgs84(window),
        stretch=_STRETCH,
        assumed_window=tessera.ASSUMED_WINDOW,
    )
    return summary.model_dump(mode="json"), cog


# --------------------------------------------------------------------------- service


async def _field_geometry(session: AsyncSession, field_id: int) -> dict:
    row = await FieldRepository(session).get(field_id)
    if row is None:
        raise FieldNotFoundError(f"Field {field_id} not found")
    return mapping(to_shape(row.geometry))  # type: ignore[arg-type]


class EmbeddingService:
    def __init__(
        self,
        session: AsyncSession,
        owner: str | None,
        reader: TesseraReader,
        store: ArtifactStore | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._session = session
        self._owner = owner or ""  # same non-NULL sentinel as ArtifactService
        self._repo = ArtifactRepository(session)
        self._reader = reader
        self._store = store or get_artifact_store()
        self._settings = settings or get_settings()

    # -- create ------------------------------------------------------------

    def _store_identity(self) -> str:
        """What the reader will actually open, from settings (never from the caller)."""
        s = self._settings
        return f"s3://{s.tessera_bucket}/{s.tessera_prefix}@{s.tessera_branch}"

    def _pin_store(self, recipe):  # noqa: ANN001, ANN202
        """Overwrite the caller's ``store_version`` with the configured store, so the
        recipe hash (the cache key) changes when the store does — and a client cannot
        pick a key that serves an artifact built from a different store."""
        return recipe.model_copy(update={"store_version": self._store_identity()})

    def _guard_pixels(self, bbox: BBox, n_years: int) -> None:
        """422 before dispatch: the window must be a single zone and fit the budget
        (each pixel-year is 128 float32 = 512 B in memory). The budget is counted on
        the projected UTM window the reader fetches, not the lon/lat rectangle: a thin
        rectangle far from its zone's central meridian is tilted, and its enclosing
        UTM rectangle is much bigger."""
        rows, cols = tessera.estimate_window_shape(bbox)  # also checks the single zone
        pixels = rows * cols * n_years
        if pixels > self._settings.tessera_layer_max_pixels:
            raise AOITooLargeError(
                f"Window is ~{pixels:,} pixel-years at {tessera.RESOLUTION_M:g} m "
                f"(limit {self._settings.tessera_layer_max_pixels:,}); use a smaller area, "
                "fewer years, or a smaller aoi_buffer_m."
            )

    async def create_field_embeddings(
        self, recipe: FieldEmbeddingsRecipe, background_tasks: BackgroundTasks
    ) -> tuple[Artifact, bool]:
        # Resolve + guard first: unknown field is a 404 and an oversized/cross-zone
        # window a 422, neither of which should become a failed job.
        geom = await _field_geometry(self._session, recipe.field_id)
        self._guard_pixels(field_read_bbox(geom, recipe), len(recipe.years))
        return await self._create_or_reuse(
            recipe, ArtifactKind.field_embeddings, background_tasks, self._build_field_embeddings
        )

    async def create_embedding_layer(
        self, recipe: EmbeddingLayerRecipe, background_tasks: BackgroundTasks
    ) -> tuple[Artifact, bool]:
        geom = (
            await _field_geometry(self._session, recipe.field_id)
            if recipe.field_id is not None
            else None
        )
        self._guard_pixels(layer_bbox(geom, recipe), 1)
        return await self._create_or_reuse(
            recipe, ArtifactKind.embedding_layer, background_tasks, self._build_embedding_layer
        )

    async def _create_or_reuse(self, recipe, kind, background_tasks, job):  # noqa: ANN001, ANN202
        recipe = self._pin_store(recipe)
        h = recipe_hash(recipe)
        existing = await self._repo.get_by_recipe(self._owner, h)
        if existing is not None:
            if existing.status != JobStatus.failed.value:
                return existing, True
            # A failed build (usually a transient store error) is retried rather than
            # served forever. reset_failed is atomic, so racing retries dispatch once.
            if await self._repo.reset_failed(existing.id):
                background_tasks.add_task(job, existing.id, recipe)
                return (await self._repo.get(existing.id)) or existing, False
            return (await self._repo.get(existing.id)) or existing, True

        artifact_id = uuid4().hex
        row = await self._repo.create_or_get(
            artifact_id, kind.value, h, recipe.model_dump(mode="json"), self._owner
        )
        if row.id == artifact_id:  # we won the insert race -> build it
            background_tasks.add_task(job, artifact_id, recipe)
            return row, False
        return row, True  # someone else created it first

    # -- background jobs ---------------------------------------------------

    async def _offload(self, fn, *args):  # noqa: ANN001, ANN202
        """Run a blocking build on the bounded read pool. ``fail_after`` only stops
        *waiting* after the deadline: it cannot kill the thread, and the pool slot
        stays taken until the read really ends. A job still queued at the deadline is
        cancelled and never starts."""
        pool = _read_executor(self._settings.tessera_max_concurrent_reads)
        with anyio.fail_after(self._settings.tessera_timeout_seconds):
            return await asyncio.get_running_loop().run_in_executor(pool, fn, *args)

    async def _fail(self, repo: ArtifactRepository, artifact_id: str, exc: BaseException) -> None:
        if isinstance(exc, FieldNotFoundError | tessera.TesseraNoDataError):
            message = str(exc)
        elif isinstance(exc, tessera.TesseraError):
            message = f"TESSERA upstream error: {exc}"
        elif isinstance(exc, TimeoutError):
            message = (
                "TESSERA upstream error: read timed out after "
                f"{self._settings.tessera_timeout_seconds:g} s"
            )
        else:
            logger.exception("Embedding build %s failed", artifact_id, exc_info=exc)
            message = "Artifact build failed."
        await repo.set_error(artifact_id, message)

    async def _build_field_embeddings(
        self, artifact_id: str, recipe: FieldEmbeddingsRecipe
    ) -> None:
        from geogent_backend.db.session import SessionLocal

        async with SessionLocal() as session:
            repo = ArtifactRepository(session)
            try:
                await repo.set_status(artifact_id, JobStatus.running.value)
                geom = await _field_geometry(session, recipe.field_id)
                summary, payload = await self._offload(
                    build_field_embeddings, self._reader, geom, recipe
                )
                # The npz is deliberately NOT an asset: the asset route serves
                # declared keys as image/tiff, and the agent only needs the summary.
                await self._store.put(artifact_id, PAYLOAD_KEY, payload)
                await repo.set_result(artifact_id, summary, [])
            except Exception as exc:  # noqa: BLE001 - every failure must end in a failed row
                await self._fail(repo, artifact_id, exc)

    async def _build_embedding_layer(self, artifact_id: str, recipe: EmbeddingLayerRecipe) -> None:
        from geogent_backend.db.session import SessionLocal

        async with SessionLocal() as session:
            repo = ArtifactRepository(session)
            try:
                await repo.set_status(artifact_id, JobStatus.running.value)
                geom = (
                    await _field_geometry(session, recipe.field_id)
                    if recipe.field_id is not None
                    else None
                )
                summary, cog = await self._offload(
                    build_embedding_layer, self._reader, layer_bbox(geom, recipe), recipe
                )
                await self._store.put(artifact_id, LAYER_KEY, cog)
                asset = ArtifactAsset(
                    role="pca_rgb",
                    key=LAYER_KEY,
                    url=_asset_url(artifact_id, LAYER_KEY),
                    media_type=_ASSET_MEDIA_TYPE,
                    colormap="rgb",
                    label=f"Embedding PCA ({recipe.year})",
                    bands=["pc1", "pc2", "pc3"],
                )
                await repo.set_result(artifact_id, summary, [asset.model_dump()])
            except Exception as exc:  # noqa: BLE001
                await self._fail(repo, artifact_id, exc)
