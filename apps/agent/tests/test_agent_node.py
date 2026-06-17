"""Unit tests for agent_node's summarizer wiring.

Deterministic and key-free: the chat model and tracing are stubbed so we assert
the summary model is selected from settings (AGENT_SUMMARY_MODEL) without any
network call.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from geogent_agent.config import get_settings
from geogent_agent.nodes import agent_node


class _FakeModel:
    def with_config(self, **_kwargs: object) -> _FakeModel:
        return self

    async def ainvoke(self, _messages: object) -> AIMessage:
        return AIMessage(content="condensed summary")


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_summarizer_uses_dedicated_model_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_SUMMARY_MODEL", "openrouter:google/gemini-2.5-flash")
    get_settings.cache_clear()
    captured: dict = {}

    def fake_get_chat_model(model: str | None = None) -> _FakeModel:
        captured["model"] = model
        return _FakeModel()

    monkeypatch.setattr(agent_node, "get_chat_model", fake_get_chat_model)
    out = await agent_node._summarize_history("", [HumanMessage(content="hi")], {})

    assert captured["model"] == "openrouter:google/gemini-2.5-flash"
    assert out == "condensed summary"


@pytest.mark.asyncio
async def test_summarizer_falls_back_to_main_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_SUMMARY_MODEL", raising=False)
    get_settings.cache_clear()
    captured: dict = {}

    def fake_get_chat_model(model: str | None = None) -> _FakeModel:
        captured["model"] = model
        return _FakeModel()

    monkeypatch.setattr(agent_node, "get_chat_model", fake_get_chat_model)
    await agent_node._summarize_history("prior", [HumanMessage(content="hi")], {})

    # None => get_chat_model resolves the default agent model.
    assert captured["model"] is None
