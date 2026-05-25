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
