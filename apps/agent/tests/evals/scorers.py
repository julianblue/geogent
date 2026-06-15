"""Pure, offline scorers over an agent trajectory.

A *trajectory* is the dict returned by ``client.threads.get_state(thread_id)``:
``{"values": {"messages": [...]}, ...}``. Every scorer takes that dict plus the
relevant slice of an :class:`~tests.evals.dataset.Expectation` and returns a
``ScoreResult`` (score in {0, 1} + a human-readable reason). No scorer touches
a live client, so they're fully unit-testable from canned fixtures with no key.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from tests.evals.dataset import ArgConstraint

# ---------------------------------------------------------------------------
# Trajectory extraction helpers
# ---------------------------------------------------------------------------


def _messages(trajectory: dict[str, Any]) -> list[dict[str, Any]]:
    return [m for m in trajectory.get("values", {}).get("messages", []) if isinstance(m, dict)]


def iter_tool_calls(trajectory: dict[str, Any]) -> list[dict[str, Any]]:
    """Every tool call across the thread, in order, as ``{name, args}`` dicts."""
    calls: list[dict[str, Any]] = []
    for message in _messages(trajectory):
        for call in message.get("tool_calls") or []:
            if isinstance(call, dict) and "name" in call:
                calls.append(call)
    return calls


def tool_names(trajectory: dict[str, Any]) -> list[str]:
    return [c["name"] for c in iter_tool_calls(trajectory)]


def final_assistant_text(trajectory: dict[str, Any]) -> str:
    for message in reversed(_messages(trajectory)):
        if message.get("type") != "ai":
            continue
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content
        if isinstance(content, list):
            parts = [
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            ]
            joined = "".join(parts).strip()
            if joined:
                return joined
    return ""


def count_steps(trajectory: dict[str, Any]) -> int:
    """Number of agent steps = number of AI messages (LLM turns) in the thread."""
    return sum(1 for m in _messages(trajectory) if m.get("type") == "ai")


# ---------------------------------------------------------------------------
# Scorers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScoreResult:
    score: int  # 0 or 1
    reason: str

    def __bool__(self) -> bool:
        return self.score == 1


def score_tool_selection(
    trajectory: dict[str, Any], tools_required: Iterable[str | list[str]]
) -> ScoreResult:
    """1 iff every requirement is met.

    A requirement is either a tool name (that tool must be invoked) or a list of
    tool names (an *any-of* group: at least one must be invoked). The any-of
    form mirrors the e2e suite, where some prompts have two equally valid tool
    paths (e.g. server-side ``buffer_geometry`` vs. UI ``add_buffer_layer``).
    """
    required = list(tools_required)
    if not required:
        return ScoreResult(1, "no tools required")
    invoked = set(tool_names(trajectory))
    missing: list[str | list[str]] = []
    for req in required:
        if isinstance(req, list):
            if not any(t in invoked for t in req):
                missing.append(req)
        elif req not in invoked:
            missing.append(req)
    if missing:
        return ScoreResult(
            0, f"unmet tool requirement(s) {missing}; invoked {sorted(invoked) or '[]'}"
        )
    return ScoreResult(1, f"tool requirements met: {required}")


def score_tools_forbidden(
    trajectory: dict[str, Any], tools_forbidden: Iterable[str]
) -> ScoreResult:
    """1 iff none of the forbidden tools were invoked.

    The guardrail complement of ``score_tool_selection``: asserts the agent did
    NOT reach for a tool it shouldn't have — e.g. used the data-returning
    ``features_within`` rather than the display-only ``list_features_in_viewport``,
    or asked for clarification on an ambiguous request instead of acting on a
    guess.
    """
    forbidden = set(tools_forbidden)
    if not forbidden:
        return ScoreResult(1, "no forbidden tools")
    invoked = set(tool_names(trajectory))
    used = sorted(forbidden & invoked)
    if used:
        return ScoreResult(0, f"invoked forbidden tool(s) {used}")
    return ScoreResult(1, f"avoided forbidden tools: {sorted(forbidden)}")


def _check_constraint(value: Any, c: ArgConstraint) -> tuple[bool, str]:
    if c.between is not None:
        lo, hi = c.between
        try:
            num = float(value)
        except (TypeError, ValueError):
            return False, f"{c.arg}={value!r} not numeric (want in [{lo}, {hi}])"
        if lo <= num <= hi:
            return True, f"{c.arg}={num} in [{lo}, {hi}]"
        return False, f"{c.arg}={num} outside [{lo}, {hi}]"
    # equals
    if value == c.equals:
        return True, f"{c.arg}={value!r} == {c.equals!r}"
    return False, f"{c.arg}={value!r} != {c.equals!r}"


def score_argument_correctness(
    trajectory: dict[str, Any], args: dict[str, list[ArgConstraint]]
) -> ScoreResult:
    """1 iff, for each constrained tool, *some* invocation satisfies every
    constraint on it. A tool that was never called fails its constraints.
    """
    if not args:
        return ScoreResult(1, "no argument constraints")
    calls = iter_tool_calls(trajectory)
    reasons: list[str] = []
    ok = True
    for tool, constraints in args.items():
        tool_calls = [c.get("args") or {} for c in calls if c.get("name") == tool]
        if not tool_calls:
            ok = False
            reasons.append(f"{tool}: never called")
            continue
        # A constrained tool passes if any single invocation meets all constraints.
        best_fail: list[str] | None = None
        matched = False
        for call_args in tool_calls:
            results = [_check_constraint(call_args.get(c.arg), c) for c in constraints]
            if all(passed for passed, _ in results):
                matched = True
                reasons.append(f"{tool}: " + "; ".join(msg for _, msg in results))
                break
            if best_fail is None:
                best_fail = [msg for _, msg in results]
        if not matched:
            ok = False
            reasons.append(f"{tool}: no call satisfied constraints ({'; '.join(best_fail or [])})")
    return ScoreResult(1 if ok else 0, " | ".join(reasons))


def score_trajectory_length(trajectory: dict[str, Any], max_steps: int | None) -> ScoreResult:
    """1 iff the agent finished within ``max_steps`` AI turns."""
    if max_steps is None:
        return ScoreResult(1, "no max_steps constraint")
    steps = count_steps(trajectory)
    if steps <= max_steps:
        return ScoreResult(1, f"{steps} steps <= max {max_steps}")
    return ScoreResult(0, f"{steps} steps > max {max_steps}")


def score_final_answer(
    trajectory: dict[str, Any],
    contains_any: Iterable[str],
    *,
    judge: object | None = None,
) -> ScoreResult:
    """1 iff the final assistant message contains any expected keyword
    (case-insensitive substring match).

    ``judge`` is an off-by-default hook for an LLM-as-judge. It's intentionally
    unused by the deterministic path so CI never incurs LLM cost or flakiness;
    pass a callable ``(final_text, keywords) -> bool`` to enable it locally.
    """
    keywords = [k for k in contains_any if k]
    final = final_assistant_text(trajectory)
    if not final:
        return ScoreResult(0, "no final assistant message")
    if not keywords:
        return ScoreResult(1, "no keyword constraint; final message present")

    if judge is not None:
        passed = bool(judge(final, keywords))  # type: ignore[operator]
        return ScoreResult(1 if passed else 0, f"llm-judge verdict={passed}")

    low = final.lower()
    hits = [k for k in keywords if k.lower() in low]
    if hits:
        return ScoreResult(1, f"final contains {hits}")
    return ScoreResult(0, f"final contains none of {keywords}: {final[:120]!r}")
