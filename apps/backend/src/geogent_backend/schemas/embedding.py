"""Request/summary schemas for the TESSERA embedding artifacts (ADR 0003).

Two recipe kinds join ``temporal_features`` in the artifacts registry:

- ``field_embeddings`` — per-field, per-year mean/std embedding plus the
  year-over-year change signal (the agent reads the compact ``summary``; the
  vectors live in a ``field_embeddings.npz`` payload that is *not* an asset), and
- ``embedding_layer`` — a PCA(3) false-colour GeoTIFF of one year's window (the
  ``pca_rgb`` asset the UI draws).

Both carry ``store_version`` so pointing the reader at a new store release busts
the content-addressed cache, exactly as ``recipe_version`` does for a math change.
It is informational on the wire: the service overwrites it with the configured
store (bucket/prefix/branch) before hashing, so a caller cannot choose the cache key.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator
from shapely import wkt

from geogent_backend.config import get_settings
from geogent_backend.schemas.artifact import ArtifactKind

__all__ = [
    "FieldEmbeddingsRecipe",
    "EmbeddingLayerRecipe",
    "FieldEmbeddingsSummary",
    "EmbeddingLayerSummary",
]


def _check_year(year: int, label: str) -> None:
    s = get_settings()
    if not s.tessera_min_year <= year <= s.tessera_max_year:
        raise ValueError(
            f"{label} {year} is outside the TESSERA range {s.tessera_min_year}-{s.tessera_max_year}"
        )


def _check_wgs84_bounds(west: float, south: float, east: float, north: float, label: str) -> None:
    """Finite, ordered lon/lat degrees (NaN fails every comparison, so it is rejected)."""
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError(f"{label} must be (west, south, east, north) in lon/lat degrees")


class FieldEmbeddingsRecipe(BaseModel):
    """Per-year field embedding statistics + year-over-year change for one field."""

    kind: Literal[ArtifactKind.field_embeddings] = ArtifactKind.field_embeddings
    recipe_version: int = 1
    store_version: str = "v1.1"
    field_id: int
    start_year: int = Field(ge=2017)
    end_year: int
    # "aoi" subtracts each year's mean embedding over the field's surroundings
    # before comparing years; "none" compares the raw field means.
    centring: Literal["aoi", "none"] = "aoi"
    aoi_buffer_m: int = Field(default=1000, ge=0, le=5000)  # centring window around the field
    dim: int = Field(default=128, ge=1, le=128)

    @model_validator(mode="after")
    def _check(self) -> FieldEmbeddingsRecipe:
        if self.end_year < self.start_year:
            raise ValueError("end_year must be on or after start_year")
        s = get_settings()
        span = self.end_year - self.start_year + 1
        if span > s.tessera_max_years:
            raise ValueError(f"at most {s.tessera_max_years} years per request (got {span})")
        _check_year(self.start_year, "start_year")
        _check_year(self.end_year, "end_year")
        return self

    @property
    def years(self) -> list[int]:
        return list(range(self.start_year, self.end_year + 1))


class EmbeddingLayerRecipe(BaseModel):
    """PCA false-colour layer of one year's embeddings over an AOI."""

    kind: Literal[ArtifactKind.embedding_layer] = ArtifactKind.embedding_layer
    recipe_version: int = 1
    store_version: str = "v1.1"
    mode: Literal["pca"] = "pca"
    year: int = Field(ge=2017)
    # Area of interest — exactly one of these. field_id shows the field plus
    # ``pad_m`` of context; geometry_wkt / bbox take any caller-supplied window.
    field_id: int | None = None
    geometry_wkt: str | None = None
    bbox: tuple[float, float, float, float] | None = None
    pad_m: int = Field(default=200, ge=0, le=2000)  # context around field_id
    dim: int = Field(default=128, ge=1, le=128)

    @model_validator(mode="after")
    def _check(self) -> EmbeddingLayerRecipe:
        _check_year(self.year, "year")
        provided = [self.field_id is not None, self.geometry_wkt is not None, self.bbox is not None]
        if sum(provided) != 1:
            raise ValueError("provide exactly one of field_id, geometry_wkt, bbox")
        if self.bbox is not None:
            _check_wgs84_bounds(*self.bbox, "bbox")
        if self.geometry_wkt is not None:
            try:
                geom = wkt.loads(self.geometry_wkt)
            except Exception as exc:  # noqa: BLE001 - shapely raises several types
                raise ValueError(f"geometry_wkt is not valid WKT: {exc}") from exc
            if geom.is_empty:
                raise ValueError("geometry_wkt is empty")
            # The window is read from the geometry's bounds, so they must be lon/lat too
            # (e.g. UTM metres pasted in would otherwise pick a nonsense zone).
            west, south, east, north = geom.bounds
            _check_wgs84_bounds(west, south, east, north, "geometry_wkt bounds")
        return self


class FieldYearSummary(BaseModel):
    year: int
    pixel_count: int
    # Share of the field's pixels that had no embedding (water, thin S2 coverage).
    masked_fraction: float
    mean_norm: float | None  # ‖field mean embedding‖; null when no pixel is usable
    mean_std: float | None  # per-band std across pixels, averaged over bands
    # Mean cosine distance of the field's pixels to the field mean (0 = uniform).
    heterogeneity: float | None
    usable: bool  # false below 5 embedded interior pixels


class YoYSummary(BaseModel):
    from_year: int
    to_year: int
    cosine_distance_centred: float
    cosine_distance_raw: float


class CentringSummary(BaseModel):
    mode: Literal["aoi", "none"]
    aoi_buffer_m: int
    aoi_pixels_by_year: dict[str, int]


class RotationScreen(BaseModel):
    # The year-over-year signal separated rotation reliably only for parcels of
    # at least this size (AUC 0.95 for >= 1 ha in the spike); smaller ones are noisy.
    valid: bool
    min_area_ha: float


class GridSummary(BaseModel):
    epsg: int | None
    resolution_m: float
    width: int | None = None
    height: int | None = None


class MaskingSummary(BaseModel):
    inward_buffer_m: float
    buffered: bool  # false = the buffered polygon was empty, so the unbuffered one was used


class FieldEmbeddingsSummary(BaseModel):
    """Compact summary the agent reads — deliberately no embedding vectors."""

    field_id: int
    area_ha: float
    years: list[int]
    dim: int
    store_version: str
    grid: GridSummary
    assumed_window: str
    masking: MaskingSummary
    per_year: list[FieldYearSummary]
    yoy: list[YoYSummary]
    centring: CentringSummary
    rotation_screen: RotationScreen
    payload_key: str


class EmbeddingLayerSummary(BaseModel):
    mode: Literal["pca"]
    year: int
    dim: int
    explained_variance_ratio: list[float]
    valid_fraction: float
    grid: GridSummary
    bbox_wgs84: tuple[float, float, float, float]
    stretch: str
    assumed_window: str
