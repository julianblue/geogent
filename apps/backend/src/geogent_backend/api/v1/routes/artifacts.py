"""Artifacts (data-cube) endpoints.

Mounted under ``/api/v1/analytics`` and auth-gated like the rest of analytics.
``POST`` is idempotent: an identical recipe returns the existing handle (ADR
0002 content-addressing). The agent reads ``summary``; the UI fetches the COG
via the asset route.
"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status

from geogent_backend.api.deps import CurrentUser, DbSession, get_current_user
from geogent_backend.schemas.artifact import (
    ArtifactCreateResponse,
    ArtifactKind,
    ArtifactResponse,
    ManagementZonesRecipe,
    TemporalFeaturesRecipe,
)
from geogent_backend.schemas.raster import JobStatus
from geogent_backend.services.artifact_service import AOITooLargeError, ArtifactService
from geogent_backend.services.raster_service import FieldNotFoundError
from geogent_backend.storage.artifact_store import ArtifactStoreError

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.post(
    "/temporal-features",
    response_model=ArtifactCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_temporal_features(
    payload: TemporalFeaturesRecipe,
    session: DbSession,
    user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> ArtifactCreateResponse:
    service = ArtifactService(session, owner=str(user.id))
    try:
        row, cached = await service.create_temporal_features(payload, background_tasks)
    except FieldNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AOITooLargeError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return ArtifactCreateResponse(
        artifact_id=row.id,
        kind=ArtifactKind(row.kind),
        status=JobStatus(row.status),
        cached=cached,
    )


@router.post(
    "/management-zones",
    response_model=ArtifactCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_management_zones(
    payload: ManagementZonesRecipe,
    session: DbSession,
    user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> ArtifactCreateResponse:
    service = ArtifactService(session, owner=str(user.id))
    try:
        row, cached = await service.create_management_zones(payload, background_tasks)
    except FieldNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AOITooLargeError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return ArtifactCreateResponse(
        artifact_id=row.id,
        kind=ArtifactKind(row.kind),
        status=JobStatus(row.status),
        cached=cached,
    )


@router.get("/artifacts/{artifact_id}", response_model=ArtifactResponse)
async def get_artifact(artifact_id: str, session: DbSession, user: CurrentUser) -> ArtifactResponse:
    result = await ArtifactService(session, owner=str(user.id)).get(artifact_id)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Artifact not found")
    return result


@router.get("/artifacts/{artifact_id}/assets/{key}")
async def get_artifact_asset(
    artifact_id: str, key: str, session: DbSession, user: CurrentUser
) -> Response:
    service = ArtifactService(session, owner=str(user.id))
    try:
        found = await service.get_asset(artifact_id, key)
    except ArtifactStoreError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Asset not found") from exc
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Artifact not found")
    # Media type comes from the asset the artifact declared: a zone map ships a
    # raster AND its vectorized polygons, which are not both image/tiff.
    data, media_type = found
    return Response(content=data, media_type=media_type)
