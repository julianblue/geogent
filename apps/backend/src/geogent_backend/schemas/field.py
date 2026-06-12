from datetime import datetime

from geojson_pydantic.geometries import Geometry
from pydantic import BaseModel, ConfigDict, Field, field_validator

# Fields are areas, so only polygonal geometry is accepted at the API boundary.
# The DB column itself is generic GEOMETRY; this keeps malformed input (a Point
# drawn on the map, say) from ever reaching PostGIS.
_POLYGONAL_TYPES = frozenset({"Polygon", "MultiPolygon"})


def _require_polygonal(value: Geometry) -> Geometry:
    if value.type not in _POLYGONAL_TYPES:
        raise ValueError(f"field geometry must be Polygon or MultiPolygon, got {value.type}")
    return value


class FieldBase(BaseModel):
    name: str = Field(..., max_length=255)
    crop: str | None = Field(default=None, max_length=255)
    season: str | None = Field(default=None, max_length=255)


class FieldCreate(FieldBase):
    # Accepts a GeoJSON geometry, which covers both a draw-on-map payload and a
    # GeoJSON upload. Cadastral / parcel-registry import is future work.
    geometry: Geometry

    @field_validator("geometry")
    @classmethod
    def _validate_geometry(cls, value: Geometry) -> Geometry:
        return _require_polygonal(value)


class FieldUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    crop: str | None = Field(default=None, max_length=255)
    season: str | None = Field(default=None, max_length=255)
    geometry: Geometry | None = None

    @field_validator("geometry")
    @classmethod
    def _validate_geometry(cls, value: Geometry | None) -> Geometry | None:
        if value is None:
            return None
        return _require_polygonal(value)


class FieldRead(FieldBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    geometry: Geometry
    created_at: datetime


class CropStat(BaseModel):
    """One row of the per-crop aggregation over a bbox (see /fields/crop-stats)."""

    crop: str
    parcels: int
    total_area_ha: float
