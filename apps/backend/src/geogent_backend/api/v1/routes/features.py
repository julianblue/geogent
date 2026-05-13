from fastapi import APIRouter

from geogent_backend.api.deps import CurrentUser, DbSession
from geogent_backend.schemas.feature import FeatureCreate, FeatureRead
from geogent_backend.services.feature_service import FeatureService

router = APIRouter()


# GET is intentionally unauthenticated: the LangGraph agent (`apps/agent`)
# enumerates features through this endpoint without a user token. Switch to a
# service-account JWT for the agent before gating GET.
@router.get("", response_model=list[FeatureRead])
async def list_features(session: DbSession) -> list[FeatureRead]:
    return await FeatureService(session).list_features()


@router.post("", response_model=FeatureRead, status_code=201)
async def create_feature(
    payload: FeatureCreate,
    session: DbSession,
    _user: CurrentUser,
) -> FeatureRead:
    return await FeatureService(session).create_feature(payload)
