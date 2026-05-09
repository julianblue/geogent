"""Tests for the model-name resolution in `geogent_agent.models.chat`.

Specifically, verify the backward-compatibility fallback: if a user has set
``BEDROCK_MODEL_ID`` but never ``AGENT_MODEL``, ``get_chat_model()`` (called
with no arguments) should resolve to the Bedrock model rather than silently
defaulting to Anthropic via ``AGENT_MODEL``'s default.
"""

import pytest

from geogent_agent.config import get_settings
from geogent_agent.models.chat import _resolve_model_name


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
