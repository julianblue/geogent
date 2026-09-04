from fastapi import APIRouter

from geogent_backend.api.v1.routes import (
    analytics,
    artifacts,
    auth,
    features,
    fields,
    health,
    raster,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(features.router, prefix="/features", tags=["features"])
api_router.include_router(fields.router, prefix="/fields", tags=["fields"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(raster.router, prefix="/analytics", tags=["raster"])
api_router.include_router(artifacts.router, prefix="/analytics", tags=["artifacts"])
