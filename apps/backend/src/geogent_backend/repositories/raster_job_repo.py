"""Persistence for raster background jobs and the per-scene zonal-stats cache."""

from __future__ import annotations

from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from geogent_backend.models.raster_job import RasterJob, RasterStatCache


class RasterJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, job_id: str, field_id: int, params: dict[str, Any]) -> RasterJob:
        row = RasterJob(id=job_id, status="pending", field_id=field_id, params=params)
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return row

    async def get(self, job_id: str) -> RasterJob | None:
        return await self._session.get(RasterJob, job_id)

    async def set_status(self, job_id: str, status: str) -> None:
        await self._session.execute(
            update(RasterJob).where(RasterJob.id == job_id).values(status=status)
        )
        await self._session.commit()

    async def set_result(self, job_id: str, result: dict[str, Any]) -> None:
        await self._session.execute(
            update(RasterJob)
            .where(RasterJob.id == job_id)
            .values(status="succeeded", result=result, error=None)
        )
        await self._session.commit()

    async def set_error(self, job_id: str, error: str) -> None:
        await self._session.execute(
            update(RasterJob).where(RasterJob.id == job_id).values(status="failed", error=error)
        )
        await self._session.commit()


class RasterStatCacheRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, cache_key: str) -> RasterStatCache | None:
        return await self._session.get(RasterStatCache, cache_key)

    async def put(self, cache_key: str, stats: dict[str, Any], histogram: dict[str, Any]) -> None:
        # The cache is keyed on immutable inputs (scene + polygon + index + bins),
        # so a concurrent insert of the same key is harmless; ignore conflicts.
        if await self._session.get(RasterStatCache, cache_key) is not None:
            return
        self._session.add(RasterStatCache(cache_key=cache_key, stats=stats, histogram=histogram))
        await self._session.commit()
