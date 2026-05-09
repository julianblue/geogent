import os

from langchain_core.language_models.chat_models import BaseChatModel

from geogent_agent.config import get_settings


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
      - "claude-*"                                  → ChatAnthropic (Anthropic API)
      - "gpt-*"                                     → ChatOpenAI (OpenAI API)
      - "bedrock:*" | "anthropic.*" | "us.anthropic.*" → ChatBedrockConverse (AWS Bedrock)

    For Bedrock, strip an optional "bedrock:" prefix; the remainder is passed
    through as the Bedrock model ID. AWS credentials are resolved via the
    standard boto3 credential chain.
    """
    settings = get_settings()
    name = model or _resolve_model_name()

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
