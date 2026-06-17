"""Request/response schemas for the artifacts (data-cube) endpoints.

An artifact is produced from a *recipe* (the normalized, hashable request) and,
once built, exposes a compact ``summary`` (for the agent) plus ``assets`` —
render URLs for the UI. M1 ships one recipe kind, ``temporal_features``: the
per-pixel "field memory" (productivity + stability) reduction of a season cube.
See ADR 0002 and docs/design/m1-artifacts-data-model.md.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from geogent_backend.geo.indices import IndexName
from geogent_backend.geo.reducers import ReducerName
from geogent_backend.schemas.raster import JobStatus

__all__ = [
    "ArtifactKind",
    "TemporalFeaturesRecipe",
    "ArtifactRecipe",
    "GridInfo",
    "FeatureStats",
    "ValidObs",
    "TemporalFeaturesSummary",
    "ArtifactAsset",
    "ArtifactCreateResponse",
    "ArtifactResponse",
]


class ArtifactKind(str, Enum):  # noqa: UP042 — str-mixin keeps JSON value as the bare string
    temporal_features = "temporal_features"


class TemporalFeaturesRecipe(BaseModel):
    """Build a season cube for one field and reduce it per pixel into the
    "field memory" layers (productivity = mean index, stability = temporal CV)."""

    kind: Literal[ArtifactKind.temporal_features] = ArtifactKind.temporal_features
    recipe_version: int = 1
    field_id: int
    index: IndexName = IndexName.ndvi
    reducer: ReducerName = ReducerName.field_memory
    reducer_params: dict[str, float] = Field(default_factory=dict)
    start_date: date
    end_date: date
    max_cloud_cover: float = Field(default=20, ge=0, le=100)
    max_scenes: int = Field(default=60, gt=0, le=200)

    @model_validator(mode="after")
    def _check_dates(self) -> TemporalFeaturesRecipe:
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


# Discriminated union grows as M2/M3 add cube / terrain / zone_map recipes.
ArtifactRecipe = TemporalFeaturesRecipe


class GridInfo(BaseModel):
    epsg: int
    resolution_m: float
    width: int
    height: int


class FeatureStats(BaseModel):
    mean: float
    min: float
    max: float
    std: float
    within_field_spread: float  # std across pixels — the "are there zones?" signal


class ValidObs(BaseModel):
    min: int
    median: int
    max: int


class TemporalFeaturesSummary(BaseModel):
    reducer: ReducerName
    index: IndexName
    n_scenes_found: int
    n_scenes_used: int
    n_scenes_failed: int
    time_span: tuple[date, date] | None
    grid: GridInfo
    valid_obs: ValidObs
    # One entry per reducer output (e.g. productivity/stability, or slope, …).
    outputs: dict[str, FeatureStats]


class ArtifactAsset(BaseModel):
    role: str
    key: str
    url: str
    media_type: str
    colormap: str = "rdylgn"
    label: str = ""
    bands: list[str] = Field(default_factory=list)


class ArtifactCreateResponse(BaseModel):
    artifact_id: str
    kind: ArtifactKind
    status: JobStatus
    cached: bool


class ArtifactResponse(BaseModel):
    id: str
    kind: ArtifactKind
    status: JobStatus
    summary: dict | None = None
    assets: list[ArtifactAsset] = Field(default_factory=list)
    error: str | None = None
