from fastapi import APIRouter
from pydantic import BaseModel, Field

from geogent_backend.api.deps import DbSession
from geogent_backend.geo.operations import (
    area_of,
    buffer_geometry,
    distance_between,
    features_within,
    geometries_intersect,
)

router = APIRouter()


class BufferRequest(BaseModel):
    geometry_wkt: str = Field(
        ...,
        description="Input geometry as WKT (e.g. 'POINT(-122.42 37.77)').",
    )
    distance_m: float = Field(..., gt=0, description="Buffer distance in meters.")


class BufferResponse(BaseModel):
    buffered_wkt: str


@router.post("/buffer", response_model=BufferResponse)
async def buffer(payload: BufferRequest, session: DbSession) -> BufferResponse:
    buffered_wkt = await buffer_geometry(session, payload.geometry_wkt, payload.distance_m)
    return BufferResponse(buffered_wkt=buffered_wkt)


class DistanceRequest(BaseModel):
    a_wkt: str = Field(..., description="First geometry as WKT (SRID 4326).")
    b_wkt: str = Field(..., description="Second geometry as WKT (SRID 4326).")


class DistanceResponse(BaseModel):
    distance_m: float


@router.post("/distance", response_model=DistanceResponse)
async def distance(payload: DistanceRequest, session: DbSession) -> DistanceResponse:
    meters = await distance_between(session, payload.a_wkt, payload.b_wkt)
    return DistanceResponse(distance_m=meters)


class AreaRequest(BaseModel):
    geometry_wkt: str = Field(
        ...,
        description="Polygon or multipolygon as WKT (SRID 4326).",
    )


class AreaResponse(BaseModel):
    area_m2: float


@router.post("/area", response_model=AreaResponse)
async def area(payload: AreaRequest, session: DbSession) -> AreaResponse:
    m2 = await area_of(session, payload.geometry_wkt)
    return AreaResponse(area_m2=m2)


class IntersectsRequest(BaseModel):
    a_wkt: str = Field(..., description="First geometry as WKT (SRID 4326).")
    b_wkt: str = Field(..., description="Second geometry as WKT (SRID 4326).")


class IntersectsResponse(BaseModel):
    intersects: bool


@router.post("/intersects", response_model=IntersectsResponse)
async def intersects(payload: IntersectsRequest, session: DbSession) -> IntersectsResponse:
    hit = await geometries_intersect(session, payload.a_wkt, payload.b_wkt)
    return IntersectsResponse(intersects=hit)


class FeaturesWithinRequest(BaseModel):
    geometry_wkt: str = Field(
        ...,
        description="Search area as WKT (SRID 4326). Features fully inside are returned.",
    )


class FeatureRef(BaseModel):
    id: int
    name: str


class FeaturesWithinResponse(BaseModel):
    features: list[FeatureRef]


@router.post("/features-within", response_model=FeaturesWithinResponse)
async def features_within_route(
    payload: FeaturesWithinRequest, session: DbSession
) -> FeaturesWithinResponse:
    rows = await features_within(session, payload.geometry_wkt)
    return FeaturesWithinResponse(features=[FeatureRef(**r) for r in rows])
