from fastapi import APIRouter

from geogent_backend.api.v1.routes import analytics, features, health

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(features.router, prefix="/features", tags=["features"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
