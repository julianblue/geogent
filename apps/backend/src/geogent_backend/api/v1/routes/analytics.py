from fastapi import APIRouter
from pydantic import BaseModel, Field

from geogent_backend.api.deps import DbSession
from geogent_backend.geo.operations import buffer_geometry

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
