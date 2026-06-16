"""Unit tests for conversation history trimming (context/cost control).

Deterministic and key-free: `trim_history` uses a char-based heuristic, so these
assert the structural guarantees that keep a trimmed thread valid for
tool-calling (start on a human turn; never orphan a ToolMessage).
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage

from geogent_agent.utils.context import (
    approx_token_count,
    partition_history,
    render_messages,
    summarize_and_partition,
    trim_history,
)


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


def test_single_oversized_turn_falls_back_to_last_turn() -> None:
    # The most recent turn alone exceeds the budget. The fallback keeps only the
    # suffix from the last human message — NOT the full history — so an oversized
    # turn doesn't re-stack older turns on top of itself.
    msgs = [*_turn(0, big=True), *_turn(1, big=True)]
    trimmed = trim_history(msgs, 100)
    assert trimmed == msgs[4:]  # only the second (last) turn
    assert isinstance(trimmed[0], HumanMessage)
    assert len(trimmed) < len(msgs)


# --- summarizing trimmer -----------------------------------------------------


def test_partition_under_budget_keeps_after_watermark() -> None:
    msgs = [*_turn(0), *_turn(1)]
    # Nothing over budget: prefix already summarized (4) stays summarized.
    assert partition_history(msgs, 0, 12000) == (0, msgs)
    assert partition_history(msgs, 4, 12000) == (4, msgs[4:])


def test_partition_over_budget_splits_on_human_and_is_monotonic() -> None:
    msgs = [m for i in range(30) for m in _turn(i, big=True)]
    split, kept = partition_history(msgs, summarized_count=0, max_tokens=6000)
    assert split > 0
    assert isinstance(msgs[split], HumanMessage)  # kept window starts on human
    assert kept == msgs[split:]
    # Never moves below an existing watermark.
    split2, _ = partition_history(msgs, summarized_count=split + 4, max_tokens=6000)
    assert split2 >= split + 4


def test_render_messages_includes_tool_calls_and_text() -> None:
    rendered = render_messages(_turn(0))
    assert "User: question 0" in rendered
    assert "Assistant: [called list_features({})]" in rendered
    assert "Assistant: answer 0" in rendered


async def _fake_summarizer_factory() -> tuple[list, object]:
    calls: list[tuple[str, list[AnyMessage]]] = []

    async def summarizer(prior: str, new: list[AnyMessage]) -> str:
        calls.append((prior, new))
        return f"{prior}|summarized {len(new)}".lstrip("|")

    return calls, summarizer


@pytest.mark.asyncio
async def test_summarize_skips_when_nothing_dropped() -> None:
    calls, summarizer = await _fake_summarizer_factory()
    msgs = [*_turn(0), *_turn(1)]
    kept, summary, count = await summarize_and_partition(msgs, "", 0, 12000, summarizer)
    assert kept == msgs
    assert (summary, count) == ("", 0)
    assert calls == []  # summarizer not called when under budget


@pytest.mark.asyncio
async def test_summarize_folds_new_messages_and_advances_watermark() -> None:
    calls, summarizer = await _fake_summarizer_factory()
    msgs = [m for i in range(30) for m in _turn(i, big=True)]
    kept, summary, count = await summarize_and_partition(msgs, "", 0, 6000, summarizer)
    assert len(calls) == 1
    prior, folded = calls[0]
    assert prior == ""
    assert folded == msgs[:count]  # exactly the dropped prefix
    assert kept == msgs[count:]
    assert "summarized" in summary
    assert count > 0


@pytest.mark.asyncio
async def test_summarize_failure_keeps_unsummarized_verbatim() -> None:
    async def boom(prior: str, new: list[AnyMessage]) -> str:
        raise RuntimeError("model down")

    msgs = [m for i in range(30) for m in _turn(i, big=True)]
    kept, summary, count = await summarize_and_partition(msgs, "prev", 4, 6000, boom)
    # Degrade safely: summary/watermark unchanged, nothing un-summarized is lost.
    assert (summary, count) == ("prev", 4)
    assert kept == msgs[4:]
