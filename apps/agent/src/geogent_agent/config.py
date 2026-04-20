from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    agent_model: str = Field(default="claude-sonnet-4-6")
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    backend_url: str = Field(default="http://localhost:8000")

    langsmith_api_key: str | None = None
    langsmith_tracing: bool = False
    langsmith_project: str = "geogent"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
