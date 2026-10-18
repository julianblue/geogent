"""TESSERA embedding endpoints (ADR 0003).

Mounted under ``/api/v1/analytics`` and auth-gated like the rest of analytics.
Both ``POST``s are idempotent content-addressed creates that answer 202 with an
artifact handle; the client then polls the generic ``GET /artifacts/{id}`` and
fetches the PCA COG through the existing asset route (see ``artifacts.py``).

The store reader comes in through :func:`get_tessera_reader`, so a disabled or
unavailable TESSERA setup is a 503 raised *before* any work, and tests override it.
"""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from geogent_backend.api.deps import CurrentUser, DbSession, get_current_user
from geogent_backend.config import get_settings
from geogent_backend.geo import tessera
from geogent_backend.geo.tessera import TesseraReader
from geogent_backend.models.artifact import Artifact
from geogent_backend.schemas.artifact import ArtifactCreateResponse, ArtifactKind
from geogent_backend.schemas.embedding import EmbeddingLayerRecipe, FieldEmbeddingsRecipe
from geogent_backend.schemas.raster import JobStatus
from geogent_backend.services.artifact_service import AOITooLargeError
from geogent_backend.services.embedding_service import EmbeddingService
from geogent_backend.services.raster_service import FieldNotFoundError

router = APIRouter(dependencies=[Depends(get_current_user)])

_reader: TesseraReader | None = None


def get_tessera_reader() -> TesseraReader:
    """The process-wide store reader, or 503 when TESSERA is disabled / not installed."""
    global _reader
    settings = get_settings()
    if not settings.tessera_enabled:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="TESSERA embeddings are disabled (TESSERA_ENABLED=false).",
        )
    try:
        tessera.ensure_available()
    except tessera.TesseraUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    if _reader is None:
        _reader = tessera.reader_from_settings(settings)
    return _reader


def _created(row: Artifact, cached: bool) -> ArtifactCreateResponse:
    return ArtifactCreateResponse(
        artifact_id=row.id,
        kind=ArtifactKind(row.kind),
        status=JobStatus(row.status),
        cached=cached,
    )


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, FieldNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, AOITooLargeError | tessera.TesseraZoneError):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
    return HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"TESSERA upstream error: {exc}")


@router.post(
    "/field-embeddings",
    response_model=ArtifactCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_field_embeddings(
    payload: FieldEmbeddingsRecipe,
    session: DbSession,
    user: CurrentUser,
    background_tasks: BackgroundTasks,
    reader: Annotated[TesseraReader, Depends(get_tessera_reader)],
) -> ArtifactCreateResponse:
    service = EmbeddingService(session, owner=str(user.id), reader=reader)
    try:
        row, cached = await service.create_field_embeddings(payload, background_tasks)
    except (FieldNotFoundError, AOITooLargeError, tessera.TesseraError) as exc:
        raise _http_error(exc) from exc
    return _created(row, cached)


@router.post(
    "/embedding-layers",
    response_model=ArtifactCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_embedding_layer(
    payload: EmbeddingLayerRecipe,
    session: DbSession,
    user: CurrentUser,
    background_tasks: BackgroundTasks,
    reader: Annotated[TesseraReader, Depends(get_tessera_reader)],
) -> ArtifactCreateResponse:
    service = EmbeddingService(session, owner=str(user.id), reader=reader)
    try:
        row, cached = await service.create_embedding_layer(payload, background_tasks)
    except (FieldNotFoundError, AOITooLargeError, tessera.TesseraError) as exc:
        raise _http_error(exc) from exc
    return _created(row, cached)
