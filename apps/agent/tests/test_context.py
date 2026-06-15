"""Unit tests for conversation history trimming (context/cost control).

Deterministic and key-free: `trim_history` uses a char-based heuristic, so these
assert the structural guarantees that keep a trimmed thread valid for
tool-calling (start on a human turn; never orphan a ToolMessage).
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from geogent_agent.utils.context import approx_token_count, trim_history


def _turn(i: int, *, big: bool = False) -> list:
    """One user→tool→assistant round, optionally with a large tool payload."""
    payload = ("x" * 4000) if big else "ok"
    return [
        HumanMessage(content=f"question {i}"),
        AIMessage(content="", tool_calls=[{"name": "list_features", "args": {}, "id": f"c{i}"}]),
        ToolMessage(content=payload, tool_call_id=f"c{i}"),
        AIMessage(content=f"answer {i}"),
    ]


def test_short_history_is_unchanged() -> None:
    msgs = [HumanMessage(content="hi"), AIMessage(content="hello")]
    assert trim_history(msgs, 12000) == msgs


def test_disabled_returns_all() -> None:
    msgs = [m for i in range(20) for m in _turn(i, big=True)]
    assert trim_history(msgs, 0) is not msgs  # returns a copy
    assert trim_history(msgs, 0) == msgs


def test_long_history_trimmed_within_budget() -> None:
    msgs = [m for i in range(30) for m in _turn(i, big=True)]
    budget = 6000
    trimmed = trim_history(msgs, budget)
    assert 0 < len(trimmed) < len(msgs)
    assert approx_token_count(trimmed) <= budget


def test_trimmed_window_starts_on_human_and_pairs_tools() -> None:
    msgs = [m for i in range(30) for m in _turn(i, big=True)]
    trimmed = trim_history(msgs, 6000)
    # Must begin on a human turn so the window is a valid conversation prefix.
    assert isinstance(trimmed[0], HumanMessage)
    # No ToolMessage may appear before its AIMessage tool_call (no orphans):
    open_tool_call_ids: set[str] = set()
    for m in trimmed:
        if isinstance(m, AIMessage):
            for call in m.tool_calls or []:
                open_tool_call_ids.add(call["id"])
        elif isinstance(m, ToolMessage):
            assert m.tool_call_id in open_tool_call_ids, "orphaned ToolMessage in trimmed window"


def test_single_oversized_turn_falls_back_to_original() -> None:
    # The most recent (and only) turn alone exceeds the budget: rather than
    # return an empty/invalid window, keep the original so the user's request
    # still reaches the model.
    msgs = _turn(0, big=True)
    assert trim_history(msgs, 100) == msgs
