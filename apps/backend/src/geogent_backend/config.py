from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_JWT_DEFAULTS = frozenset(
    {
        "change-me-in-prod",  # config.py field default
        "dev-only-change-me",  # .env.example / docker-compose default
        "",
    }
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "geogent-backend"
    app_env: str = "development"
    log_level: str = "INFO"

    database_url: str = Field(
        default="postgresql+asyncpg://geogent:geogent@localhost:5432/geogent",
        description="Async SQLAlchemy URL (asyncpg driver).",
    )
    database_url_sync: str = Field(
        default="postgresql+psycopg://geogent:geogent@localhost:5432/geogent",
        description="Sync SQLAlchemy URL used by Alembic.",
    )

    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000"],
    )

    jwt_secret_key: str = Field(
        default="change-me-in-prod",
        description="HMAC key for HS256 JWTs. MUST be overridden in production.",
    )
    jwt_algorithm: str = Field(default="HS256")
    jwt_access_token_expire_minutes: int = Field(default=60 * 24)

    stac_api_url: str = Field(
        default="https://earth-search.aws.element84.com/v1",
        description="Root URL of the STAC API used to discover Sentinel-2 scenes.",
    )
    stac_collection: str = Field(default="sentinel-2-l2a")
    raster_max_scenes: int = Field(default=60)
    raster_job_concurrency: int = Field(default=4)

    # --- Data cubes / artifacts (#65, ADR 0002) ------------------------------
    # Heavy cube outputs (stability/zone COGs) are written here and served back
    # via the artifacts route. A local filesystem store keeps v1 dependency-free;
    # swap ArtifactStore for an S3/MinIO impl behind the same interface later.
    artifact_storage_dir: str = Field(
        default="/tmp/geogent-artifacts",
        description="Directory the local ArtifactStore writes COG assets under.",
    )
    cube_resolution_m: float = Field(
        default=10.0,
        description="Target ground resolution (m) of the canonical cube grid.",
    )
    cube_max_scenes: int = Field(
        default=120,
        description="Cap on scenes stacked into one cube (cost guard).",
    )
    cube_max_pixels: int = Field(
        default=4_000_000,
        description="Reject (422) AOIs whose grid would exceed this many pixels "
        "at cube_resolution_m — the in-process path is field/farm-scale only.",
    )

    # --- TESSERA yearly embeddings (ADR 0003) --------------------------------
    # Read anonymously from the public Icechunk store on AWS Open Data. The
    # bucket/prefix/branch are folded into every recipe hash server-side, so
    # pointing at another store busts caches.
    tessera_enabled: bool = Field(
        default=True,
        description="Kill switch: when false the embedding routes answer 503.",
    )
    tessera_bucket: str = Field(default="tessera-embeddings")
    tessera_prefix: str = Field(default="v1.1/dclimate.icechunk")
    tessera_region: str = Field(default="us-west-2")
    tessera_branch: str = Field(default="main")
    tessera_min_year: int = Field(default=2017, description="First year in the store.")
    tessera_max_year: int = Field(default=2025, description="Latest year in the store.")
    tessera_max_years: int = Field(
        default=9, description="Cap on the number of years in one field_embeddings request."
    )
    tessera_timeout_seconds: float = Field(
        default=120.0, description="Deadline for one blocking store read (per background job)."
    )
    tessera_layer_max_pixels: int = Field(
        default=1_000_000,
        description="Reject (422) embedding windows above this many 10 m pixels "
        "(x years for field_embeddings) — each pixel-year is 512 B of float32.",
    )
    tessera_max_concurrent_reads: int = Field(
        default=2, description="Store reads allowed in flight at once (worker-thread limiter)."
    )
    tessera_year_threads: int = Field(
        default=4, description="Threads used to fetch the years of one window in parallel."
    )

    # --- Routing / geocoding providers (#55) ---------------------------------
    # All pluggable + self-hostable via env. Defaults point at the public OSM
    # demo services; respect their usage policies and swap to a self-hosted
    # instance for anything beyond light/interactive use.
    osrm_base_url: str = Field(
        default="https://router.project-osrm.org",
        description="OSRM routing server (route + table). The public demo serves "
        "the 'driving' profile only; self-host for walking/cycling.",
    )
    nominatim_base_url: str = Field(
        default="https://nominatim.openstreetmap.org",
        description="Nominatim geocoder base URL (forward + reverse).",
    )
    geocoder_user_agent: str = Field(
        default="geogent-backend/0.5 (+https://github.com/julianblue/geogent)",
        description="User-Agent sent to Nominatim, as its usage policy requires.",
    )
    ors_base_url: str = Field(
        default="https://api.openrouteservice.org",
        description="OpenRouteService base URL — used for isochrones, which OSRM "
        "cannot compute natively.",
    )
    ors_api_key: str | None = Field(
        default=None,
        description="OpenRouteService API key. Isochrone requests return 503 "
        "until this is set (or ORS_BASE_URL points at a keyless self-host).",
    )
    routing_timeout_seconds: float = Field(default=30.0)

    @model_validator(mode="after")
    def _reject_weak_jwt_secret_outside_development(self) -> "Settings":
        if self.app_env != "development" and self.jwt_secret_key in _DEV_JWT_DEFAULTS:
            raise ValueError(
                "JWT_SECRET_KEY must be a strong, explicit value when APP_ENV != 'development'. "
                "Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(48))'"
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
