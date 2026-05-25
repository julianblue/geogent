from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from geogent_backend.api.v1.router import api_router
from geogent_backend.config import get_settings
from geogent_backend.core.logging import configure_logging
from geogent_backend.geo.operations import GeometryValidationError
from geogent_backend.geo.raster import RasterComputeError


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api/v1")

    @app.exception_handler(GeometryValidationError)
    async def _geometry_validation_handler(
        _request: Request, exc: GeometryValidationError
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(RasterComputeError)
    async def _raster_compute_handler(_request: Request, exc: RasterComputeError) -> JSONResponse:
        # An upstream COG/STAC read or zonal reduction failed.
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    return app


app = create_app()
