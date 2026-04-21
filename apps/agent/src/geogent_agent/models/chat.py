from langchain_core.language_models.chat_models import BaseChatModel

from geogent_agent.config import get_settings


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
    name = model or settings.agent_model

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
