from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
