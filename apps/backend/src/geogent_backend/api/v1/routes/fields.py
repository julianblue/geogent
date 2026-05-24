from fastapi import APIRouter, Depends, HTTPException, Query, status

from geogent_backend.api.deps import DbSession, get_current_user
from geogent_backend.schemas.field import FieldCreate, FieldRead, FieldUpdate
from geogent_backend.services.field_service import FieldService

# Unlike /features (GET is open for the agent), every field route is auth-gated.
router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[FieldRead])
async def list_fields(session: DbSession) -> list[FieldRead]:
    return await FieldService(session).list_fields()


# Declared before /{field_id} so "in-bbox" isn't parsed as an int path param.
@router.get("/in-bbox", response_model=list[FieldRead])
async def fields_in_bbox(
    session: DbSession,
    min_lon: float = Query(..., ge=-180, le=180),
    min_lat: float = Query(..., ge=-90, le=90),
    max_lon: float = Query(..., ge=-180, le=180),
    max_lat: float = Query(..., ge=-90, le=90),
) -> list[FieldRead]:
    return await FieldService(session).fields_in_bbox(min_lon, min_lat, max_lon, max_lat)


@router.post("", response_model=FieldRead, status_code=201)
async def create_field(payload: FieldCreate, session: DbSession) -> FieldRead:
    return await FieldService(session).create_field(payload)


@router.get("/{field_id}", response_model=FieldRead)
async def get_field(field_id: int, session: DbSession) -> FieldRead:
    field = await FieldService(session).get_field(field_id)
    if field is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Field not found")
    return field


@router.patch("/{field_id}", response_model=FieldRead)
async def update_field(field_id: int, payload: FieldUpdate, session: DbSession) -> FieldRead:
    field = await FieldService(session).update_field(field_id, payload)
    if field is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Field not found")
    return field


@router.delete("/{field_id}", status_code=204)
async def delete_field(field_id: int, session: DbSession) -> None:
    deleted = await FieldService(session).delete_field(field_id)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Field not found")
