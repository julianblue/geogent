"""Orchestration for the raster-compute endpoints.

Resolves field polygons and STAC scenes, shares a Postgres result cache between
the synchronous zonal-stats path and the background time-series job, and offloads
the blocking GDAL/numpy compute onto a worker thread so the event loop never
blocks.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import date
from typing import Any
from uuid import UUID, uuid4

import anyio
from fastapi import BackgroundTasks
from geoalchemy2.shape import to_shape
from shapely.geometry import mapping
from sqlalchemy.ext.asyncio import AsyncSession

from geogent_backend.config import get_settings
from geogent_backend.geo import phenology, raster, stac
from geogent_backend.geo.indices import IndexName
from geogent_backend.models.raster_job import RasterStatCache
from geogent_backend.repositories.field_repo import FieldRepository
from geogent_backend.repositories.raster_job_repo import (
    RasterJobRepository,
    RasterStatCacheRepository,
)
from geogent_backend.schemas.raster import (
    CurvePoint,
    Histogram,
    JobStatus,
    SceneRef,
    SeasonAnalysisJobResponse,
    SeasonAnalysisRequest,
    SeasonAnalysisResultResponse,
    TimeSeriesJobResponse,
    TimeSeriesPoint,
    TimeSeriesRequest,
    TimeSeriesResultResponse,
    ZonalStats,
    ZonalStatsRequest,
    ZonalStatsResponse,
)

logger = logging.getLogger(__name__)


# Bumped whenever the raster math changes in a way that invalidates stored
# results. v2 = per-pixel cloud/shadow masking (#65 M1): pre-mask cached means
# are biased low on partly-clouded scenes, so they must not be served.
_STAT_CACHE_VERSION = 2


# Job kinds share the raster_jobs table; params carry the kind so a job id
# can't be read back through the wrong endpoint.
_KIND_TIME_SERIES = "time_series"
_KIND_SEASON_ANALYSIS = "season_analysis"


class FieldNotFoundError(Exception):
    """The requested field id does not exist."""


def _as_series(points: list[TimeSeriesPoint]) -> list[phenology.SeriesPoint]:
    """Time-series points → the (date, value) pairs the phenology math works on."""
    return [phenology.SeriesPoint(day=p.datetime.date(), value=p.mean) for p in points]


def _shift_years(day: date, years: int) -> date:
    """``day`` moved back ``years`` calendar years (29 Feb → 28 Feb)."""
    try:
        return day.replace(year=day.year - years)
    except ValueError:
        return day.replace(year=day.year - years, day=28)


def _scene_ref(item: dict) -> SceneRef:
    props = item.get("properties") or {}
    return SceneRef(
        id=item["id"],
        datetime=props["datetime"],
        cloud_cover=float(props.get("eo:cloud_cover") or 0.0),
        epsg=props.get("proj:epsg"),
    )


class RasterService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._fields = FieldRepository(session)
        self._cache = RasterStatCacheRepository(session)
        self._jobs = RasterJobRepository(session)
        self._settings = get_settings()

    async def _load_geometry(self, field_id: int) -> dict:
        row = await self._fields.get(field_id)
        if row is None:
            raise FieldNotFoundError(f"Field {field_id} not found")
        return mapping(to_shape(row.geometry))

    @staticmethod
    def _cache_key(scene_id: str, index: IndexName, geom_4326: dict, histogram_bins: int) -> str:
        from shapely.geometry import shape

        wkb_hex = shape(geom_4326).wkb_hex
        raw = "|".join(
            [str(_STAT_CACHE_VERSION), scene_id, index.value, wkb_hex, str(histogram_bins)]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def _compute_with_cache(
        self,
        cache: RasterStatCacheRepository,
        geom_4326: dict,
        scene_item: dict,
        index: IndexName,
        histogram_bins: int,
        db_lock: asyncio.Lock | None = None,
    ) -> tuple[dict, dict, bool]:
        """Return ``(stats, histogram, cached)`` for one (scene, polygon, index).

        ``db_lock`` serializes access to the (single, non-reentrant) async DB
        session when this runs under the time-series fan-out; the expensive
        windowed read still runs concurrently via ``to_thread``.
        """
        key = self._cache_key(scene_item["id"], index, geom_4326, histogram_bins)

        async def _get() -> RasterStatCache | None:
            if db_lock is not None:
                async with db_lock:
                    return await cache.get(key)
            return await cache.get(key)

        hit = await _get()
        if hit is not None:
            return dict(hit.stats), dict(hit.histogram), True

        result = await anyio.to_thread.run_sync(
            raster.zonal_stats, geom_4326, scene_item, index, histogram_bins
        )
        histogram = result.pop("histogram")
        stats = result
        if db_lock is not None:
            async with db_lock:
                await cache.put(key, stats, histogram)
        else:
            await cache.put(key, stats, histogram)
        return stats, histogram, False

    async def _series_points(
        self,
        cache: RasterStatCacheRepository,
        geom_4326: dict,
        scenes: list[dict],
        index: IndexName,
    ) -> list[TimeSeriesPoint]:
        """Zonal-reduce every scene into one time-series point, concurrently.

        Shared by the time-series job and the season analysis. Scenes whose read
        fails (fully clouded polygon, missing asset) are dropped rather than
        failing the job — a season is still readable with a few holes in it, and
        the caller can see how many points survived.
        """
        sem = asyncio.Semaphore(self._settings.raster_job_concurrency)
        db_lock = asyncio.Lock()

        async def _point(scene_item: dict) -> TimeSeriesPoint | None:
            async with sem:
                try:
                    stats, _hist, _cached = await self._compute_with_cache(
                        cache,
                        geom_4326,
                        scene_item,
                        index,
                        histogram_bins=20,
                        db_lock=db_lock,
                    )
                except raster.RasterComputeError:
                    return None
            props = scene_item.get("properties") or {}
            return TimeSeriesPoint(
                scene_id=scene_item["id"],
                datetime=props["datetime"],
                cloud_cover=float(props.get("eo:cloud_cover") or 0.0),
                mean=stats["mean"],
                min=stats["min"],
                max=stats["max"],
                std=stats["std"],
                valid_pixels=stats["valid_pixels"],
            )

        results = await asyncio.gather(*[_point(s) for s in scenes])
        return sorted((p for p in results if p is not None), key=lambda p: p.datetime)

    async def zonal_stats(self, req: ZonalStatsRequest) -> ZonalStatsResponse:
        geom_4326 = await self._load_geometry(req.field_id)

        if req.scene_id:
            scene_item = await stac.get_item(self._settings.stac_collection, req.scene_id)
        else:
            from shapely.geometry import shape

            bbox = list(shape(geom_4326).bounds)
            scene_item = await stac.find_scene(
                bbox, datetime=req.datetime, max_cloud_cover=req.max_cloud_cover
            )

        stats, histogram, cached = await self._compute_with_cache(
            self._cache, geom_4326, scene_item, req.index, req.histogram_bins
        )

        return ZonalStatsResponse(
            field_id=req.field_id,
            index=req.index,
            scene=_scene_ref(scene_item),
            stats=ZonalStats(**stats),
            histogram=Histogram(**histogram),
            cached=cached,
        )

    async def start_time_series(
        self, req: TimeSeriesRequest, background_tasks: BackgroundTasks
    ) -> TimeSeriesJobResponse:
        job_id = uuid4().hex
        params = {**json.loads(req.model_dump_json()), "kind": _KIND_TIME_SERIES}
        await self._jobs.create(job_id, req.field_id, params)
        background_tasks.add_task(self._run_time_series, job_id, req)
        return TimeSeriesJobResponse(job_id=UUID(job_id), status=JobStatus.pending)

    async def _run_time_series(self, job_id: str, req: TimeSeriesRequest) -> None:
        # The background task outlives the request, so it must use its own session.
        from geogent_backend.db.session import SessionLocal

        async with SessionLocal() as session:
            jobs = RasterJobRepository(session)
            cache = RasterStatCacheRepository(session)
            fields = FieldRepository(session)
            try:
                await jobs.set_status(job_id, JobStatus.running.value)

                row = await fields.get(req.field_id)
                if row is None:
                    raise FieldNotFoundError(f"Field {req.field_id} not found")
                geom_4326 = mapping(to_shape(row.geometry))

                from shapely.geometry import shape

                bbox = list(shape(geom_4326).bounds)
                max_scenes = min(req.max_scenes, self._settings.raster_max_scenes)
                scenes = await stac.search_scenes(
                    bbox,
                    req.start_date,
                    req.end_date,
                    max_cloud_cover=req.max_cloud_cover,
                    limit=max_scenes,
                )

                points = await self._series_points(cache, geom_4326, scenes, req.index)

                result: dict[str, Any] = {
                    "field_id": req.field_id,
                    "index": req.index.value,
                    "params": json.loads(req.model_dump_json()),
                    "points": [json.loads(p.model_dump_json()) for p in points],
                }
                await jobs.set_result(job_id, result)
            except FieldNotFoundError as exc:
                # Safe to surface: it only names the requested field id.
                await jobs.set_error(job_id, str(exc))
            except Exception:
                # Log the full exception server-side; never leak internal detail
                # (upstream URLs, file paths, library messages) to the API caller.
                logger.exception("Time-series job %s failed", job_id)
                await jobs.set_error(job_id, "Time-series computation failed.")

    async def get_time_series(self, job_id: UUID) -> TimeSeriesResultResponse | None:
        row = await self._jobs.get(job_id.hex)
        # Lenient on absent kind: jobs created before kinds existed are
        # time-series jobs. Only an explicitly different kind is rejected, so a
        # season-analysis id can't be read back as a (silently empty) series.
        if row is None or (row.params or {}).get("kind", _KIND_TIME_SERIES) != _KIND_TIME_SERIES:
            return None
        result = row.result or {}
        points = [TimeSeriesPoint(**p) for p in result.get("points", [])]
        return TimeSeriesResultResponse(
            job_id=job_id,
            status=JobStatus(row.status),
            field_id=row.field_id,
            index=IndexName(result.get("index", row.params.get("index", "ndvi"))),
            params=result.get("params", row.params),
            points=points,
            error=row.error,
        )

    # --- season analysis ---------------------------------------------------

    async def start_season_analysis(
        self, req: SeasonAnalysisRequest, background_tasks: BackgroundTasks
    ) -> SeasonAnalysisJobResponse:
        job_id = uuid4().hex
        params = {**json.loads(req.model_dump_json()), "kind": _KIND_SEASON_ANALYSIS}
        await self._jobs.create(job_id, req.field_id, params)
        background_tasks.add_task(self._run_season_analysis, job_id, req)
        return SeasonAnalysisJobResponse(job_id=UUID(job_id), status=JobStatus.pending)

    async def _run_season_analysis(self, job_id: str, req: SeasonAnalysisRequest) -> None:
        from geogent_backend.db.session import SessionLocal

        async with SessionLocal() as session:
            jobs = RasterJobRepository(session)
            cache = RasterStatCacheRepository(session)
            fields = FieldRepository(session)
            try:
                await jobs.set_status(job_id, JobStatus.running.value)

                row = await fields.get(req.field_id)
                if row is None:
                    raise FieldNotFoundError(f"Field {req.field_id} not found")
                geom_4326 = mapping(to_shape(row.geometry))

                from shapely.geometry import shape

                bbox = list(shape(geom_4326).bounds)
                max_scenes = min(req.max_scenes, self._settings.raster_max_scenes)

                async def _window(start: date, end: date) -> list[TimeSeriesPoint]:
                    scenes = await stac.search_scenes(
                        bbox,
                        start,
                        end,
                        max_cloud_cover=req.max_cloud_cover,
                        limit=max_scenes,
                    )
                    return await self._series_points(cache, geom_4326, scenes, req.index)

                points = await _window(req.start_date, req.end_date)

                # The same calendar window in each preceding year. Read
                # sequentially: each window already fans out internally, and
                # stacking them would multiply concurrent COG reads.
                baselines: dict[int, list[phenology.SeriesPoint]] = {}
                baseline_origins: dict[int, date] = {}
                for k in range(1, req.baseline_years + 1):
                    start = _shift_years(req.start_date, k)
                    end = _shift_years(req.end_date, k)
                    baselines[start.year] = _as_series(await _window(start, end))
                    baseline_origins[start.year] = start

                season = _as_series(points)
                metrics = phenology.season_metrics(
                    season, req.start_date, smoothing_days=req.smoothing_days
                )
                anomaly: dict = {}
                if req.baseline_years:
                    anomaly = phenology.baseline_anomaly(
                        season,
                        req.start_date,
                        baselines,
                        baseline_origins,
                        smoothing_days=req.smoothing_days,
                    )

                curve: list[dict] = []
                if len(season) >= phenology.MIN_POINTS_FOR_SHAPE:
                    grid, smoothed = phenology.daily_curve(
                        season, req.start_date, req.smoothing_days
                    )
                    curve = phenology.sample_curve(grid, smoothed, req.start_date)

                result: dict[str, Any] = {
                    "field_id": req.field_id,
                    "index": req.index.value,
                    "params": {**json.loads(req.model_dump_json()), "kind": _KIND_SEASON_ANALYSIS},
                    "points": [json.loads(p.model_dump_json()) for p in points],
                    "curve": curve,
                    "phenology": metrics,
                    "anomaly": anomaly,
                }
                await jobs.set_result(job_id, result)
            except FieldNotFoundError as exc:
                await jobs.set_error(job_id, str(exc))
            except Exception:
                logger.exception("Season-analysis job %s failed", job_id)
                await jobs.set_error(job_id, "Season analysis failed.")

    async def get_season_analysis(self, job_id: UUID) -> SeasonAnalysisResultResponse | None:
        row = await self._jobs.get(job_id.hex)
        if row is None or (row.params or {}).get("kind") != _KIND_SEASON_ANALYSIS:
            return None
        result = row.result or {}
        return SeasonAnalysisResultResponse(
            job_id=job_id,
            status=JobStatus(row.status),
            field_id=row.field_id,
            index=IndexName(result.get("index", row.params.get("index", "ndvi"))),
            params=result.get("params", row.params),
            points=[TimeSeriesPoint(**p) for p in result.get("points", [])],
            curve=[CurvePoint(**c) for c in result.get("curve", [])],
            phenology=result.get("phenology", {}),
            anomaly=result.get("anomaly", {}),
            error=row.error,
        )
