"""Conversation context control.

Long agent threads otherwise send the entire message history to the model on
every turn, growing token cost and latency without bound. ``trim_history``
keeps the most recent turns within a budget, structurally safe for tool-calling:
the kept window always starts on a human message, so an ``AIMessage`` with
``tool_calls`` is never separated from its following ``ToolMessage`` (which the
provider would reject).

The trim is deterministic and provider-agnostic — token counting uses a simple
~4-chars/token heuristic rather than a model tokenizer — so the behaviour is
unit-testable with no key and identical across model backends.

``summarize_and_partition`` builds on that seam: instead of silently dropping
older turns, it folds them into a running LLM summary so their gist survives.
Crucially it **never prunes the message state** — the UI renders the transcript
from ``messages`` — it only shapes what the model receives this turn. A
``summarized_count`` watermark in graph state means each turn re-summarizes only
the *newly* dropped messages (incremental, cheap), not the whole prefix.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence

from langchain_core.messages import AnyMessage, HumanMessage, trim_messages

# Folds the prior summary + the newly-dropped messages into an updated summary.
Summarizer = Callable[[str, list[AnyMessage]], Awaitable[str]]


def approx_token_count(messages: Sequence[AnyMessage]) -> int:
    """Deterministic ~4-chars/token estimate, plus a small per-message overhead.

    Counts string content and any tool-call payloads (which carry real tokens).
    Good enough to bound history growth; not a billing-accurate tokenizer.
    """
    chars = 0
    for m in messages:
        content = m.content
        chars += len(content) if isinstance(content, str) else len(str(content))
        tool_calls = getattr(m, "tool_calls", None)
        if tool_calls:
            chars += len(str(tool_calls))
    return chars // 4 + len(messages) * 4


def trim_history(messages: Sequence[AnyMessage], max_tokens: int) -> list[AnyMessage]:
    """Trim conversation history to roughly ``max_tokens`` (heuristic) tokens.

    Keeps the most recent messages, anchored to start on a human turn so tool
    call/result pairs stay intact. ``max_tokens <= 0`` disables trimming.

    If even the latest turn exceeds the budget (a single huge tool result),
    ``trim_messages`` yields nothing; we then fall back to the *smallest* valid
    window — the suffix from the last human message — rather than the full
    history. Returning everything would defeat cost control and make a
    provider context-limit error more likely by stacking older turns on top of
    the oversized one. We never drop the user's current request.
    """
    msgs = list(messages)
    if max_tokens <= 0 or not msgs:
        return msgs
    if approx_token_count(msgs) <= max_tokens:
        return msgs

    trimmed = trim_messages(
        msgs,
        max_tokens=max_tokens,
        token_counter=approx_token_count,
        strategy="last",
        start_on="human",
        include_system=False,
        allow_partial=False,
    )
    if trimmed:
        return trimmed

    # Budget can't fit even the latest turn: keep just that turn (suffix from the
    # last human message), which is the minimal structurally-valid window.
    for i in range(len(msgs) - 1, -1, -1):
        if isinstance(msgs[i], HumanMessage):
            return msgs[i:]
    return msgs


_ROLE = {"human": "User", "ai": "Assistant", "tool": "Tool", "system": "System"}


def render_messages(messages: Sequence[AnyMessage]) -> str:
    """Flatten messages to ``Role: text`` lines for a summarization prompt.

    Tool calls are rendered as a compact ``Assistant: [called name(args)]`` line
    so the summary can mention what the agent did, not just what it said.
    """
    lines: list[str] = []
    for m in messages:
        role = _ROLE.get(getattr(m, "type", ""), "Message")
        content = m.content if isinstance(m.content, str) else str(m.content)
        for call in getattr(m, "tool_calls", None) or []:
            lines.append(f"{role}: [called {call.get('name')}({call.get('args')})]")
        if content.strip():
            lines.append(f"{role}: {content.strip()}")
    return "\n".join(lines)


def partition_history(
    messages: Sequence[AnyMessage], summarized_count: int, max_tokens: int
) -> tuple[int, list[AnyMessage]]:
    """Split history into a summarizable prefix and a verbatim kept suffix.

    Returns ``(split, kept)`` where ``messages[:split]`` belongs in the running
    summary and ``messages[split:]`` is sent verbatim. ``split`` is a human-turn
    boundary (so ``kept`` is valid for tool-calling) and never moves backwards
    below ``summarized_count`` — once a message is summarized it stays summarized,
    so the model never sees a turn that's also folded into the summary.
    """
    msgs = list(messages)
    floor = max(0, min(summarized_count, len(msgs)))
    if max_tokens <= 0 or approx_token_count(msgs) <= max_tokens:
        return floor, msgs[floor:]
    kept = trim_history(msgs, max_tokens)
    split = max(len(msgs) - len(kept), floor)
    return split, msgs[split:]


async def summarize_and_partition(
    messages: Sequence[AnyMessage],
    summary: str,
    summarized_count: int,
    max_tokens: int,
    summarizer: Summarizer,
) -> tuple[list[AnyMessage], str, int]:
    """Return ``(model_messages, new_summary, new_summarized_count)``.

    Folds any newly-dropped messages into the running summary via ``summarizer``
    and returns the verbatim suffix to send. If the summarizer raises, we degrade
    gracefully: keep everything not already summarized verbatim and leave the
    summary/watermark untouched, so a flaky summarizer never loses context or
    fails the turn.
    """
    msgs = list(messages)
    split, kept = partition_history(msgs, summarized_count, max_tokens)
    new_messages = msgs[summarized_count:split]
    if not new_messages:
        return kept, summary, summarized_count
    try:
        new_summary = await summarizer(summary, new_messages)
    except Exception:  # noqa: BLE001 - never fail a turn on summarization
        return msgs[summarized_count:], summary, summarized_count
    return kept, new_summary, split
