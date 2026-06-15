"""Conversation context control.

Long agent threads otherwise send the entire message history to the model on
every turn, growing token cost and latency without bound. ``trim_history``
keeps the most recent turns within a budget, structurally safe for tool-calling:
the kept window always starts on a human message, so an ``AIMessage`` with
``tool_calls`` is never separated from its following ``ToolMessage`` (which the
provider would reject).

Trimming is deterministic and provider-agnostic — token counting uses a simple
~4-chars/token heuristic rather than a model tokenizer — so the behaviour is
unit-testable with no key and identical across model backends. (A summarizing
trimmer that folds dropped turns into a synopsis is a natural future extension;
this module is the structural seam for it.)
"""

from __future__ import annotations

from collections.abc import Sequence

from langchain_core.messages import AnyMessage, trim_messages


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
    call/result pairs stay intact. ``max_tokens <= 0`` disables trimming. If even
    the latest turn exceeds the budget (a single huge tool result), the original
    history is returned unchanged rather than an empty/invalid window — better to
    send a large turn than to drop the user's actual request.
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
    return trimmed or msgs
