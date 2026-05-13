from fastapi import APIRouter, HTTPException, status

from geogent_backend.api.deps import CurrentUser, DbSession
from geogent_backend.schemas.auth import LoginRequest, TokenResponse
from geogent_backend.schemas.user import UserRead
from geogent_backend.services.auth_service import AuthError, AuthService

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, session: DbSession) -> TokenResponse:
    service = AuthService(session)
    try:
        user = await service.authenticate(payload.email, payload.password)
    except AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return service.issue_token(user)


@router.get("/me", response_model=UserRead)
async def me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)
