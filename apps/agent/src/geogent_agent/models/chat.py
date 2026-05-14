import os

from langchain_core.language_models.chat_models import BaseChatModel

from geogent_agent.config import get_settings


def infer_provider(name: str) -> str:
    """Return a stable provider label for the given model name.

    Used as a LangSmith tag/metadata field so traces are filterable by
    backend regardless of which model slug they used. Mirrors the dispatch
    in ``get_chat_model``.
    """
    if name.startswith("openrouter:"):
        return "openrouter"
    if (
        name.startswith("bedrock:")
        or name.startswith("anthropic.")
        or name.startswith("us.anthropic.")
    ):
        return "bedrock"
    if name.startswith("claude"):
        return "anthropic"
    if name.startswith("gpt"):
        return "openai"
    return "unknown"


def _resolve_model_name() -> str:
    """Resolve the model name to use when none is passed explicitly.

    Falls back to ``BEDROCK_MODEL_ID`` when the user has set it but not
    ``AGENT_MODEL`` — this preserves the previous classic-agent behavior for
    Bedrock-only setups, where ``BEDROCK_MODEL_ID`` was the only knob.
    """
    settings = get_settings()
    if os.getenv("AGENT_MODEL") is None and os.getenv("BEDROCK_MODEL_ID") is not None:
        return settings.bedrock_model_id
    return settings.agent_model


def get_chat_model(model: str | None = None) -> BaseChatModel:
    """Return a configured chat model based on the agent settings.

    Dispatches by model-name prefix:
      - "openrouter:<vendor>/<model>"                  → ChatOpenAI via OpenRouter
      - "claude-*"                                     → ChatAnthropic (Anthropic API)
      - "gpt-*"                                        → ChatOpenAI (OpenAI API)
      - "bedrock:*" | "anthropic.*" | "us.anthropic.*" → ChatBedrockConverse (AWS Bedrock)

    For Bedrock, strip an optional "bedrock:" prefix; the remainder is passed
    through as the Bedrock model ID. AWS credentials are resolved via the
    standard boto3 credential chain.

    For OpenRouter, strip the "openrouter:" prefix; the remainder is the
    OpenRouter model slug (e.g. "anthropic/claude-3.5-sonnet"). Requires
    OPENROUTER_API_KEY. Base URL defaults to https://openrouter.ai/api/v1
    and can be overridden via OPENROUTER_BASE_URL.
    """
    settings = get_settings()
    name = model or _resolve_model_name()

    if name.startswith("openrouter:"):
        from langchain_openai import ChatOpenAI

        if not settings.openrouter_api_key:
            raise ValueError(
                "OPENROUTER_API_KEY is required when AGENT_MODEL uses the 'openrouter:' prefix"
            )
        return ChatOpenAI(
            model=name.removeprefix("openrouter:"),
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            temperature=0,
        )

    if (
        name.startswith("bedrock:")
        or name.startswith("anthropic.")
        or name.startswith("us.anthropic.")
    ):
        from langchain_aws import ChatBedrockConverse

        model_id = name.removeprefix("bedrock:") if name.startswith("bedrock:") else name
        return ChatBedrockConverse(
            model=model_id,
            region_name=settings.aws_region,
            temperature=0,
        )

    if name.startswith("claude"):
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=name, temperature=0)

    if name.startswith("gpt"):
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=name, temperature=0)

    raise ValueError(f"Unsupported AGENT_MODEL: {name!r}")
