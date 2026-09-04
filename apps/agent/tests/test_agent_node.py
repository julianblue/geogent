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


class _FakeToolBoundModel:
    """Mimics ``get_chat_model().bind_tools(...)`` — records whether tools were
    ever bound, since that's the mechanism the step cap relies on."""

    def __init__(self, sink: dict) -> None:
        self._sink = sink

    def bind_tools(self, tools: object) -> _FakeToolBoundModel:
        self._sink["bound_tools"] = tools
        return self

    def with_config(self, **_kwargs: object) -> _FakeToolBoundModel:
        return self

    async def ainvoke(self, messages: object) -> AIMessage:
        self._sink["messages"] = messages
        return AIMessage(content="final answer", tool_calls=[])


def _ai_with_tool_call() -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": "geocode_place", "args": {"query": "x"}, "id": "1"}],
    )


@pytest.mark.asyncio
async def test_agent_node_binds_tools_under_the_step_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_MAX_TOOL_STEPS", "20")
    get_settings.cache_clear()
    sink: dict = {}
    monkeypatch.setattr(agent_node, "get_chat_model", lambda *_a, **_k: _FakeToolBoundModel(sink))

    state = {"messages": [HumanMessage(content="hi")]}
    await agent_node.agent_node(state, config=None)

    assert "bound_tools" in sink


@pytest.mark.asyncio
async def test_agent_node_disables_tools_once_the_step_cap_is_reached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The regression this guards: a LangGraph Platform worker was observed
    re-invoking this node ~550 times for one turn without the framework's
    recursion_limit ever firing. Once the turn's own step count reaches the
    cap, this node must stop offering tools so the graph is structurally
    forced to END on the next step, regardless of what the framework does."""
    monkeypatch.setenv("AGENT_MAX_TOOL_STEPS", "3")
    get_settings.cache_clear()
    sink: dict = {}
    monkeypatch.setattr(agent_node, "get_chat_model", lambda *_a, **_k: _FakeToolBoundModel(sink))

    # 3 AI turns with tool calls since the human message == at the cap.
    state = {
        "messages": [
            HumanMessage(content="do the thing"),
            _ai_with_tool_call(),
            _ai_with_tool_call(),
            _ai_with_tool_call(),
        ]
    }
    result = await agent_node.agent_node(state, config=None)

    assert "bound_tools" not in sink  # tools were never bound this call
    response = result["messages"][0]
    assert response.tool_calls == []  # structurally cannot loop again
    # The model was told plainly why tools are off.
    system_message = sink["messages"][0]
    assert "Tools are disabled" in system_message.content


def test_tool_steps_this_turn_counts_only_since_the_last_human_message() -> None:
    from geogent_agent.nodes.agent_node import _tool_steps_this_turn

    messages = [
        HumanMessage(content="turn 1"),
        _ai_with_tool_call(),
        _ai_with_tool_call(),
        HumanMessage(content="turn 2"),
        _ai_with_tool_call(),
    ]
    assert _tool_steps_this_turn(messages) == 1
