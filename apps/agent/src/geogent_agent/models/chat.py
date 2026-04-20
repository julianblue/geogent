from langchain_core.language_models.chat_models import BaseChatModel

from geogent_agent.config import get_settings


def get_chat_model(model: str | None = None) -> BaseChatModel:
    """Return a configured chat model based on the agent settings.

    Dispatches by model-name prefix:
      - "claude-*" → ChatAnthropic
      - "gpt-*"    → ChatOpenAI
    """
    settings = get_settings()
    name = model or settings.agent_model

    if name.startswith("claude"):
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=name, temperature=0)
    if name.startswith("gpt"):
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=name, temperature=0)

    raise ValueError(f"Unsupported AGENT_MODEL: {name!r}")
