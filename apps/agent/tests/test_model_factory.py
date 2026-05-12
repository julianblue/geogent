"""Tests for the model-name resolution and provider routing in
``geogent_agent.models.chat``.
"""

import pytest

from geogent_agent.config import get_settings
from geogent_agent.models.chat import _resolve_model_name, get_chat_model


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_falls_back_to_bedrock_when_only_bedrock_model_id_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AGENT_MODEL", raising=False)
    monkeypatch.setenv("BEDROCK_MODEL_ID", "us.anthropic.claude-test-v1:0")
    assert _resolve_model_name() == "us.anthropic.claude-test-v1:0"


def test_agent_model_takes_precedence_when_both_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_MODEL", "claude-sonnet-4-6")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "us.anthropic.claude-test-v1:0")
    assert _resolve_model_name() == "claude-sonnet-4-6"


def test_uses_default_agent_model_when_neither_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AGENT_MODEL", raising=False)
    monkeypatch.delenv("BEDROCK_MODEL_ID", raising=False)
    settings = get_settings()
    assert _resolve_model_name() == settings.agent_model


def test_openrouter_prefix_routes_through_openai_client_with_custom_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``openrouter:<slug>`` should produce a ChatOpenAI bound to the OpenRouter base URL."""
    from langchain_openai import ChatOpenAI

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    model = get_chat_model("openrouter:anthropic/claude-3.5-sonnet")

    assert isinstance(model, ChatOpenAI)
    assert model.model_name == "anthropic/claude-3.5-sonnet"
    assert str(model.openai_api_base).rstrip("/") == "https://openrouter.ai/api/v1"


def test_openrouter_respects_custom_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    from langchain_openai import ChatOpenAI

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://proxy.example.com/v1")
    model = get_chat_model("openrouter:meta-llama/llama-3-70b-instruct")

    assert isinstance(model, ChatOpenAI)
    assert str(model.openai_api_base).rstrip("/") == "https://proxy.example.com/v1"


def test_openrouter_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY is required"):
        get_chat_model("openrouter:anthropic/claude-3.5-sonnet")
