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
    bedrock_model_id: str = Field(
        default="us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    )
    aws_region: str = Field(default="us-east-1")

    backend_url: str = Field(default="http://localhost:8000")

    langsmith_api_key: str | None = None
    langsmith_tracing: bool = False
    langsmith_project: str = "geogent"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
