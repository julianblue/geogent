"""Request/response schemas for the raster-compute endpoints.

Flat and chart-ready by design: the time-series points and zonal histogram are
shaped for direct consumption by the agent tools (#23) and UI widgets (#24).
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field

from geogent_backend.geo.indices import IndexName

__all__ = [
    "IndexName",
    "ZonalStatsRequest",
    "SceneRef",
    "ZonalStats",
    "Histogram",
    "ZonalStatsResponse",
    "TimeSeriesRequest",
    "JobStatus",
    "TimeSeriesJobResponse",
    "TimeSeriesPoint",
    "TimeSeriesResultResponse",
]


class ZonalStatsRequest(BaseModel):
    field_id: int
    index: IndexName = IndexName.ndvi
    scene_id: str | None = None
    datetime: str | None = None
    max_cloud_cover: float = Field(default=20, ge=0, le=100)
    histogram_bins: int = Field(default=20, gt=0, le=256)


class SceneRef(BaseModel):
    id: str
    datetime: datetime
    cloud_cover: float
    epsg: int | None = None


class ZonalStats(BaseModel):
    mean: float
    min: float
    max: float
    std: float
    valid_pixels: int
    nodata_pixels: int


class Histogram(BaseModel):
    bin_edges: list[float]
    counts: list[int]


class ZonalStatsResponse(BaseModel):
    field_id: int
    index: IndexName
    scene: SceneRef
    stats: ZonalStats
    histogram: Histogram
    cached: bool


class TimeSeriesRequest(BaseModel):
    field_id: int
    index: IndexName = IndexName.ndvi
    start_date: date
    end_date: date
    max_cloud_cover: float = Field(default=20, ge=0, le=100)
    max_scenes: int = Field(default=60, gt=0, le=200)


class JobStatus(str, Enum):  # noqa: UP042 — str-mixin keeps JSON value as the bare string
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class TimeSeriesJobResponse(BaseModel):
    job_id: UUID
    status: JobStatus


class TimeSeriesPoint(BaseModel):
    scene_id: str
    datetime: datetime
    cloud_cover: float
    mean: float
    min: float
    max: float
    std: float
    valid_pixels: int


class TimeSeriesResultResponse(BaseModel):
    job_id: UUID
    status: JobStatus
    field_id: int
    index: IndexName
    params: dict
    points: list[TimeSeriesPoint]
    error: str | None = None
