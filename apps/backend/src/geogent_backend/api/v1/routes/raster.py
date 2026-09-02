"""Raster-compute endpoints: synchronous zonal stats + background time-series.

Mounted under ``/api/v1/analytics`` and auth-gated like the rest of analytics.
Routes are thin: they delegate to :class:`RasterService` and translate a missing
field/job into a 404.
"""

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from geogent_backend.api.deps import DbSession, get_current_user
from geogent_backend.schemas.raster import (
    SeasonAnalysisJobResponse,
    SeasonAnalysisRequest,
    SeasonAnalysisResultResponse,
    TimeSeriesJobResponse,
    TimeSeriesRequest,
    TimeSeriesResultResponse,
    ZonalStatsRequest,
    ZonalStatsResponse,
)
from geogent_backend.services.raster_service import FieldNotFoundError, RasterService

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.post("/zonal-stats", response_model=ZonalStatsResponse)
async def zonal_stats(payload: ZonalStatsRequest, session: DbSession) -> ZonalStatsResponse:
    try:
        return await RasterService(session).zonal_stats(payload)
    except FieldNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/time-series", response_model=TimeSeriesJobResponse, status_code=202)
async def start_time_series(
    payload: TimeSeriesRequest,
    session: DbSession,
    background_tasks: BackgroundTasks,
) -> TimeSeriesJobResponse:
    try:
        return await RasterService(session).start_time_series(payload, background_tasks)
    except FieldNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/time-series/{job_id}", response_model=TimeSeriesResultResponse)
async def get_time_series(job_id: UUID, session: DbSession) -> TimeSeriesResultResponse:
    result = await RasterService(session).get_time_series(job_id)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Job not found")
    return result


@router.post("/season-analysis", response_model=SeasonAnalysisJobResponse, status_code=202)
async def start_season_analysis(
    payload: SeasonAnalysisRequest,
    session: DbSession,
    background_tasks: BackgroundTasks,
) -> SeasonAnalysisJobResponse:
    try:
        return await RasterService(session).start_season_analysis(payload, background_tasks)
    except FieldNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/season-analysis/{job_id}", response_model=SeasonAnalysisResultResponse)
async def get_season_analysis(job_id: UUID, session: DbSession) -> SeasonAnalysisResultResponse:
    result = await RasterService(session).get_season_analysis(job_id)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Job not found")
    return result
