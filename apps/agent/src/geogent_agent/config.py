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

    # Conversation context budget (#agent-quality). Before each model call the
    # graph trims older history to roughly this many tokens (a deterministic
    # ~4-chars/token heuristic), keeping the system prompt and the most recent
    # turns. Bounds token cost/latency on long threads. Set <= 0 to disable.
    agent_max_history_tokens: int = Field(default=12000)

    # When true, history that exceeds the budget is folded into a running LLM
    # summary (one extra, incremental model call per over-budget turn) rather
    # than silently dropped, so older context survives in condensed form. When
    # false, the agent falls back to the structural drop-only trim above.
    agent_history_summarize: bool = Field(default=True)

    # Optional dedicated model for history summarization. Summarization is a
    # cheap, mechanical task, so pointing it at a smaller/faster model than
    # AGENT_MODEL cuts the incremental cost/latency of the summarizing trimmer.
    # When unset, summarization reuses the main agent model. Same name format as
    # AGENT_MODEL (e.g. "openrouter:google/gemini-2.5-flash").
    agent_summary_model: str | None = Field(default=None)

    # Amazon Bedrock. Credentials are resolved via the standard boto3
    # chain (env vars, shared config, instance/task role) — not stored here.
    bedrock_model_id: str = Field(default="us.anthropic.claude-sonnet-4-5-20250929-v1:0")
    aws_region: str = Field(default="us-east-1")

    # OpenRouter (https://openrouter.ai) — OpenAI-compatible gateway that
    # fronts many providers. Selected by AGENT_MODEL="openrouter:<vendor>/<model>",
    # e.g. "openrouter:google/gemini-2.5-flash".
    openrouter_api_key: str | None = None
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1")

    backend_url: str = Field(default="http://localhost:8000")

    # Service-account credentials the agent uses to authenticate to the
    # backend's auth-gated endpoints. The password is intentionally unset here;
    # supply it via BACKEND_SERVICE_PASSWORD (see .env.example, which carries the
    # dev user's value for local work). Keeping the secret out of source avoids
    # baking a credential into the repo.
    backend_service_email: str = Field(default="julian.blau@googlemail.com")
    backend_service_password: str = Field(default="")

    # Postgres checkpointer (langgraph-checkpoint-postgres). Plain libpq DSN
    # (postgresql://...), distinct from backend's SQLAlchemy URL which embeds
    # the asyncpg driver (postgresql+asyncpg://...). When unset the
    # checkpointer factory raises — `langgraph dev` and unit tests rely on
    # the runtime's default in-memory saver instead.
    agent_database_url: str | None = Field(default=None)
    agent_db_schema: str = Field(default="langgraph")
    agent_db_pool_min: int = Field(default=1)
    agent_db_pool_max: int = Field(default=5)

    # LangSmith observability. These fields are reference-only: the LangChain
    # tracer reads `LANGSMITH_*` directly from `os.environ` at import time,
    # so operators must set them in the deployment environment. The fields
    # exist so `observability.py` can validate the setup at startup and so
    # the values appear in a single, typed surface for tooling.
    langsmith_api_key: str | None = None
    langsmith_tracing: bool = False
    langsmith_project: str = "geogent"
    langsmith_endpoint: str | None = None
    langsmith_sampling_rate: float | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
