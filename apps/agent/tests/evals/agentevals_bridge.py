"""Bridge the runner's ``threads.get_state`` dict to agentevals / openevals.

Everything here consumes the same trajectory dict the runner returns
(``{"values": {"messages": [...]}, ...}``) and stays import-safe offline:

- ``to_openai_messages`` / ``extract_graph_trajectory`` convert that dict into
  the two shapes agentevals understands — an OpenAI-style message list for the
  trajectory-match evaluators, and an agentevals ``GraphTrajectory``
  (inputs / results / steps) for its graph-trajectory evaluators.
- ``score_trajectory_match`` wraps agentevals'
  ``create_trajectory_match_evaluator`` (superset mode, tool args ignored —
  the deterministic args scorer owns argument checking) and grades a
  trajectory against a reference synthesized from a case's ``tools_required``.
- ``create_final_answer_judge`` builds an openevals LLM-as-judge for final
  answer quality, used on cases whose free-form output (numbers, lists) makes
  keyword checks meaningless. Only calling the judge touches the network;
  constructing everything else is pure.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable
from typing import Any

from agentevals.graph_trajectory.strict import graph_trajectory_strict_match
from agentevals.trajectory.match import create_trajectory_match_evaluator
from agentevals.types import GraphTrajectory

from tests.evals.dataset import EvalCase
from tests.evals.scorers import ScoreResult, final_assistant_text, tool_names

# ---------------------------------------------------------------------------
# Trajectory conversion
# ---------------------------------------------------------------------------

_ROLE_BY_TYPE = {"human": "user", "ai": "assistant", "tool": "tool", "system": "system"}


def _state_messages(trajectory: dict[str, Any]) -> list[dict[str, Any]]:
    return [m for m in trajectory.get("values", {}).get("messages", []) if isinstance(m, dict)]


def _text_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    return "" if content is None else str(content)


def to_openai_messages(trajectory: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert ``threads.get_state`` messages to OpenAI chat-completion dicts.

    The SDK serializes LangChain messages as ``{"type": "ai", "tool_calls":
    [{"name", "args", "id"}], ...}``; agentevals' normalizers want role-based
    OpenAI messages with function-style tool calls, so we re-shape here.
    Missing ids (hand-authored fixtures) are backfilled deterministically.
    """
    messages: list[dict[str, Any]] = []
    for idx, msg in enumerate(_state_messages(trajectory)):
        role = _ROLE_BY_TYPE.get(msg.get("type") or "")
        if role is None:
            continue
        converted: dict[str, Any] = {"role": role, "content": _text_content(msg.get("content"))}
        if role == "assistant":
            tool_calls = [
                {
                    "type": "function",
                    "id": call.get("id") or f"call_{idx}_{j}",
                    "function": {
                        "name": call["name"],
                        "arguments": json.dumps(call.get("args") or {}),
                    },
                }
                for j, call in enumerate(msg.get("tool_calls") or [])
                if isinstance(call, dict) and "name" in call
            ]
            if tool_calls:
                converted["tool_calls"] = tool_calls
        elif role == "tool":
            converted["tool_call_id"] = msg.get("tool_call_id") or ""
        messages.append(converted)
    return messages


def extract_graph_trajectory(trajectory: dict[str, Any]) -> GraphTrajectory:
    """Rebuild an agentevals ``GraphTrajectory`` from the final state dict.

    agentevals' own ``extract_langgraph_trajectory_from_thread`` walks
    checkpoint history on an in-process graph, which the SDK's
    ``threads.get_state`` doesn't expose. We reconstruct the per-turn node
    steps from the message sequence instead: each human message opens a turn
    (``__start__``), each AI message is an ``agent`` step, and each contiguous
    block of tool messages a ``tools`` step — mirroring the agent/tools layout
    of the geogent graph. Good enough for graph-trajectory evaluators and for
    logging a compact trajectory to LangSmith.
    """
    inputs: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    steps: list[list[str]] = []
    for msg in to_openai_messages(trajectory):
        role = msg["role"]
        if role == "user" or not steps:
            inputs.append({"role": "user", "content": msg["content"]} if role == "user" else {})
            results.append({})
            steps.append(["__start__"])
        if role == "assistant":
            steps[-1].append("agent")
            results[-1] = {"messages": [msg]}
        elif role == "tool" and steps[-1][-1] != "tools":
            steps[-1].append("tools")
    return GraphTrajectory(inputs=inputs, results=results, steps=steps)


# ---------------------------------------------------------------------------
# Trajectory match (agentevals, deterministic)
# ---------------------------------------------------------------------------

# Superset: the agent must have made at least the reference tool calls, in any
# order, with any arguments. Order and argument checking stay with the
# deterministic scorers, so this adds agentevals' matching semantics without
# double-grading.
_trajectory_match = create_trajectory_match_evaluator(
    trajectory_match_mode="superset",
    tool_args_match_mode="ignore",
)


def reference_tool_names(case: EvalCase, invoked: Iterable[str]) -> list[str]:
    """Resolve ``tools_required`` into concrete tool names.

    Any-of groups pick the member the agent actually invoked (falling back to
    the first listed) so a valid alternative path still matches the reference.
    """
    invoked_set = set(invoked)
    names: list[str] = []
    for req in case.expect.tools_required:
        if isinstance(req, list):
            names.append(next((t for t in req if t in invoked_set), req[0]))
        else:
            names.append(req)
    return names


def build_reference_trajectory(case: EvalCase, invoked: Iterable[str]) -> list[dict[str, Any]]:
    """Synthesize a minimal golden trajectory for one case, in OpenAI shape."""
    names = reference_tool_names(case, invoked)
    messages: list[dict[str, Any]] = [{"role": "user", "content": case.input}]
    if names:
        messages.append(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"type": "function", "id": f"ref_{i}", "function": {"name": n, "arguments": "{}"}}
                    for i, n in enumerate(names)
                ],
            }
        )
        messages.extend(
            {"role": "tool", "content": "ok", "tool_call_id": f"ref_{i}"}
            for i in range(len(names))
        )
    messages.append({"role": "assistant", "content": "Done."})
    return messages


def score_trajectory_match(trajectory: dict[str, Any], case: EvalCase) -> ScoreResult:
    """1 iff the trajectory's tool calls are a superset of the case's golden ones."""
    invoked = tool_names(trajectory)
    result = _trajectory_match(
        outputs=to_openai_messages(trajectory),
        reference_outputs=build_reference_trajectory(case, invoked),
    )
    if isinstance(result, list):
        result = result[0]
    passed = bool(result.get("score"))
    required = reference_tool_names(case, invoked)
    return ScoreResult(
        1 if passed else 0,
        f"agentevals superset match {'passed' if passed else 'failed'}: "
        f"required {required}, invoked {invoked}",
    )


def score_graph_steps(trajectory: dict[str, Any], case: EvalCase) -> ScoreResult:
    """1 iff the reconstructed graph steps strictly match the case's golden ones.

    Backed by agentevals' ``graph_trajectory_strict_match``, which compares the
    ``steps`` field turn by turn. Only meaningful for cases that pin
    ``expect.graph_steps`` (recorded from stable runs); callers gate on that.
    """
    expected = case.expect.graph_steps
    if expected is None:
        return ScoreResult(1, "no graph_steps constraint")
    actual = extract_graph_trajectory(trajectory)
    result = graph_trajectory_strict_match(
        outputs=actual,
        reference_outputs=GraphTrajectory(inputs=[], results=[], steps=expected),
    )
    if isinstance(result, list):
        result = result[0]
    passed = bool(result.get("score"))
    return ScoreResult(
        1 if passed else 0,
        f"agentevals strict graph-steps match {'passed' if passed else 'failed'}: "
        f"expected {expected}, actual {actual['steps']}",
    )


# ---------------------------------------------------------------------------
# LLM-as-judge for final answer quality (openevals)
# ---------------------------------------------------------------------------

# Used on cases where core.yaml deliberately skips final_contains_any: the
# answer is free-form numeric/list output a substring check can't grade.
FINAL_ANSWER_JUDGE_PROMPT = """\
You are grading the final answer a geospatial analytics agent gave to a user.
The agent had tools for geocoding, geometry math (buffer, area, distance,
intersection), feature storage, satellite imagery search, and map control, and
has already finished running them.

<user_request>
{inputs}
</user_request>

<final_answer>
{outputs}
</final_answer>

Grade the final answer True only if it:
- directly addresses the request with the concrete computed outcome (an actual
  distance, area, geometry description, list, or confirmation of the action
  performed) rather than a promise of future work, a question back, a refusal,
  or placeholder text;
- gives values that are plausible for the request (sensible units and orders
  of magnitude); and
- does not contradict the request.

Verbosity, rounding, formatting, and extra helpful context are all acceptable.
Otherwise grade False.
"""

# A judge takes (case, trajectory) and grades the final answer.
FinalAnswerJudge = Callable[[EvalCase, dict[str, Any]], ScoreResult]


def default_judge_model() -> str:
    """Model used to grade final answers; overridable per environment."""
    return (
        os.getenv("GEOGENT_EVAL_JUDGE_MODEL")
        or os.getenv("TEST_AGENT_MODEL")
        or "openrouter:google/gemini-2.5-flash"
    )


def make_final_answer_scorer(evaluator: Callable[..., Any]) -> FinalAnswerJudge:
    """Adapt an openevals judge into a ``(case, trajectory) -> ScoreResult`` scorer.

    Split from ``create_final_answer_judge`` so unit tests can inject a stub
    evaluator and stay offline.
    """

    def score(case: EvalCase, trajectory: dict[str, Any]) -> ScoreResult:
        final = final_assistant_text(trajectory)
        if not final:
            return ScoreResult(0, "no final assistant message to judge")
        result = evaluator(inputs=case.input, outputs=final)
        if isinstance(result, list):
            result = result[0]
        passed = bool(result.get("score"))
        comment = (result.get("comment") or "").strip()
        return ScoreResult(
            1 if passed else 0,
            f"llm-judge {'passed' if passed else 'failed'}: {comment[:300] or 'no rationale'}",
        )

    return score


def create_final_answer_judge(model: str | None = None) -> FinalAnswerJudge:
    """Build the live LLM-as-judge. Requires credentials for the judge model
    (OPENROUTER_API_KEY for the default), so call it only from the live suite.
    """
    from openevals.llm import create_llm_as_judge

    from geogent_agent.models import get_chat_model

    evaluator = create_llm_as_judge(
        prompt=FINAL_ANSWER_JUDGE_PROMPT,
        feedback_key="final_answer_quality",
        judge=get_chat_model(model or default_judge_model()),
    )
    return make_final_answer_scorer(evaluator)
