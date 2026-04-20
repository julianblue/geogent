from datetime import datetime
from typing import Any

from geojson_pydantic import Feature as GeoJSONFeature
from geojson_pydantic.geometries import Geometry
from pydantic import BaseModel, ConfigDict, Field


class FeatureBase(BaseModel):
    name: str = Field(..., max_length=255)
    properties: dict[str, Any] = Field(default_factory=dict)


class FeatureCreate(FeatureBase):
    geometry: Geometry


class FeatureRead(FeatureBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    geometry: Geometry
    created_at: datetime


class FeatureCollectionOut(BaseModel):
    type: str = "FeatureCollection"
    features: list[GeoJSONFeature]
