"""Pydantic v2 schemas for the routing / geocoding endpoints (#55)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

Profile = Literal["driving", "walking", "cycling"]


class Coordinate(BaseModel):
    longitude: float = Field(..., ge=-180, le=180)
    latitude: float = Field(..., ge=-90, le=90)

    def as_tuple(self) -> tuple[float, float]:
        return (self.longitude, self.latitude)


class RouteRequest(BaseModel):
    coordinates: Annotated[list[Coordinate], Field(min_length=2)] = Field(
        ..., description="Ordered waypoints (lon/lat); first is origin, last is destination."
    )
    profile: Profile = "driving"


class RouteResponse(BaseModel):
    distance_m: float
    duration_s: float
    profile: Profile
    # GeoJSON LineString — passed straight to the map overlay.
    geometry: dict


class MatrixRequest(BaseModel):
    coordinates: Annotated[list[Coordinate], Field(min_length=2)]
    sources: list[int] | None = Field(
        default=None, description="Indices into coordinates; null = all points."
    )
    destinations: list[int] | None = Field(default=None)
    profile: Profile = "driving"


class MatrixResponse(BaseModel):
    durations_s: list[list[float | None]] | None
    distances_m: list[list[float | None]] | None
    profile: Profile


class IsochroneRequest(BaseModel):
    longitude: float = Field(..., ge=-180, le=180)
    latitude: float = Field(..., ge=-90, le=90)
    range_minutes: Annotated[
        list[Annotated[float, Field(gt=0)]], Field(min_length=1, max_length=10)
    ] = Field(..., description="Time budgets in minutes (> 0), e.g. [5, 10, 15].")
    profile: Profile = "driving"


class IsochroneResponse(BaseModel):
    profile: Profile
    range_minutes: list[float]
    # GeoJSON FeatureCollection of reachability polygons.
    geojson: dict


class GeocodeResult(BaseModel):
    display_name: str
    longitude: float
    latitude: float
    type: str | None = None
    bbox: list[float] | None = None


class GeocodeResponse(BaseModel):
    results: list[GeocodeResult]


class ReverseGeocodeResponse(BaseModel):
    display_name: str
    longitude: float
    latitude: float
    type: str | None = None
    address: dict
