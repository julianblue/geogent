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

    # Selects the default architecture when code needs a single choice
    # (e.g. a CLI smoke test). Graphs registered in langgraph.json are
    # always available independently of this value.
    agent_architecture: str = Field(default="langgraph_react")

    # Amazon Bedrock. Credentials are resolved via the standard boto3
    # chain (env vars, shared config, instance/task role) — not stored here.
    bedrock_model_id: str = Field(default="us.anthropic.claude-sonnet-4-5-20250929-v1:0")
    aws_region: str = Field(default="us-east-1")

    # OpenRouter (https://openrouter.ai) — OpenAI-compatible gateway that
    # fronts many providers. Selected by AGENT_MODEL="openrouter:<vendor>/<model>",
    # e.g. "openrouter:anthropic/claude-3.5-sonnet".
    openrouter_api_key: str | None = None
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1")

    backend_url: str = Field(default="http://localhost:8000")

    # Postgres checkpointer (langgraph-checkpoint-postgres). Plain libpq DSN
    # (postgresql://...), distinct from backend's SQLAlchemy URL which embeds
    # the asyncpg driver (postgresql+asyncpg://...). When unset the
    # checkpointer factory raises — `langgraph dev` and unit tests rely on
    # the runtime's default in-memory saver instead.
    agent_database_url: str | None = Field(default=None, alias="AGENT_DATABASE_URL")
    agent_db_schema: str = Field(default="langgraph")
    agent_db_pool_min: int = Field(default=1)
    agent_db_pool_max: int = Field(default=5)

    langsmith_api_key: str | None = None
    langsmith_tracing: bool = False
    langsmith_project: str = "geogent"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
