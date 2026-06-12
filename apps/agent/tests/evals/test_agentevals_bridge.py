"""Offline unit tests for the agentevals/openevals bridge.

These run with NO API key: the conversion helpers and the agentevals
trajectory-match scorer are pure, and the LLM-judge plumbing is exercised by
injecting a stub evaluator into ``make_final_answer_scorer``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.evals.agentevals_bridge import (
    build_reference_trajectory,
    extract_graph_trajectory,
    make_final_answer_scorer,
    reference_tool_names,
    score_graph_steps,
    score_trajectory_match,
    to_openai_messages,
)
from tests.evals.dataset import EvalCase, load_cases
from tests.evals.report import score_case

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())


def _ai(tool_calls: list[dict] | None = None, content: str = "") -> dict[str, Any]:
    msg: dict[str, Any] = {"type": "ai", "content": content}
    if tool_calls is not None:
        msg["tool_calls"] = tool_calls
    return msg


def _traj(messages: list[dict[str, Any]]) -> dict[str, Any]:
    return {"values": {"messages": messages}}


CASES = {c.id: c for c in load_cases()}
PARIS_CASE = CASES["geocode_then_fly_to_paris"]


# --- message conversion -------------------------------------------------------


def test_to_openai_messages_roles_and_tool_calls() -> None:
    messages = to_openai_messages(_load("paris_fly_to.json"))
    assert [m["role"] for m in messages] == ["user", "assistant", "tool", "assistant", "tool", "assistant"]
    calls = [c for m in messages for c in m.get("tool_calls") or []]
    assert [c["function"]["name"] for c in calls] == ["geocode_place", "fly_to"]
    args = json.loads(calls[1]["function"]["arguments"])
    assert args["longitude"] == 2.320041


def test_to_openai_messages_backfills_missing_ids() -> None:
    # Hand-authored trajectories may omit ids; conversion must still emit the
    # fields agentevals' normalizer requires.
    traj = _traj(
        [
            _ai([{"name": "fly_to", "args": {"longitude": 1.0}}]),
            {"type": "tool", "content": "ok"},
        ]
    )
    messages = to_openai_messages(traj)
    assert all(call["id"] for m in messages for call in m.get("tool_calls") or [])
    assert messages[1]["tool_call_id"] == ""
    # The recorded bad fixture (no message ids) must normalize without error too.
    bad = to_openai_messages(_load("paris_fly_to_bad.json"))
    assert all("tool_call_id" in m for m in bad if m["role"] == "tool")


def test_to_openai_messages_flattens_content_parts() -> None:
    traj = _traj([{"type": "ai", "content": [{"type": "text", "text": "hello "}, {"type": "text", "text": "world"}]}])
    assert to_openai_messages(traj)[0]["content"] == "hello world"


# --- graph trajectory extraction ---------------------------------------------


def test_extract_graph_trajectory_steps_mirror_react_loop() -> None:
    out = extract_graph_trajectory(_load("paris_fly_to.json"))
    assert out["steps"] == [["__start__", "agent", "tools", "agent", "tools", "agent"]]
    assert out["inputs"] == [{"role": "user", "content": "Fly me to Paris, France."}]
    final = out["results"][0]["messages"][0]
    assert final["role"] == "assistant"
    assert "Paris" in final["content"]


def test_extract_graph_trajectory_collapses_contiguous_tool_steps() -> None:
    traj = _traj(
        [
            {"type": "human", "content": "hi"},
            _ai([{"name": "a", "args": {}}, {"name": "b", "args": {}}]),
            {"type": "tool", "content": "ra"},
            {"type": "tool", "content": "rb"},
            _ai(content="done"),
        ]
    )
    assert extract_graph_trajectory(traj)["steps"] == [["__start__", "agent", "tools", "agent"]]


# --- trajectory match scorer ---------------------------------------------------


def test_trajectory_match_passes_recorded_good_run() -> None:
    res = score_trajectory_match(_load("paris_fly_to.json"), PARIS_CASE)
    assert res.score == 1, res.reason


def test_trajectory_match_fails_when_required_tool_missing() -> None:
    res = score_trajectory_match(_load("paris_fly_to_bad.json"), PARIS_CASE)
    assert res.score == 0
    assert "geocode_place" in res.reason


def test_trajectory_match_resolves_any_of_to_invoked_member() -> None:
    case = CASES["buffer_viewport_overlay"]  # [[buffer_geometry, add_buffer_layer]]
    traj = _traj([_ai([{"name": "add_buffer_layer", "args": {"distance_meters": 500}}])])
    assert reference_tool_names(case, ["add_buffer_layer"]) == ["add_buffer_layer"]
    assert score_trajectory_match(traj, case).score == 1
    # Neither member invoked: reference falls back to the first and fails.
    assert reference_tool_names(case, []) == ["buffer_geometry"]
    assert score_trajectory_match(_traj([_ai(content="done")]), case).score == 0


def test_reference_trajectory_is_well_formed() -> None:
    messages = build_reference_trajectory(PARIS_CASE, [])
    assert messages[0] == {"role": "user", "content": PARIS_CASE.input}
    calls = messages[1]["tool_calls"]
    assert [c["function"]["name"] for c in calls] == ["geocode_place"]
    assert messages[-1]["role"] == "assistant"


# --- golden graph steps (strict match) -----------------------------------------

PARIS_STEPS = [["__start__", "agent", "tools", "agent", "tools", "agent"]]


def _case_with_steps(steps: list[list[str]] | None) -> EvalCase:
    return EvalCase.from_dict(
        {"id": "steps_case", "input": "x", "expect": {"graph_steps": steps} if steps else {}}
    )


def test_graph_steps_strict_match_pass_and_fail() -> None:
    good = _load("paris_fly_to.json")
    assert score_graph_steps(good, _case_with_steps(PARIS_STEPS)).score == 1
    res = score_graph_steps(good, _case_with_steps([["__start__", "agent"]]))
    assert res.score == 0
    assert "expected" in res.reason


def test_graph_steps_without_constraint_passes() -> None:
    assert score_graph_steps(_load("paris_fly_to.json"), _case_with_steps(None)).score == 1


def test_graph_steps_yaml_validation_fails_loudly() -> None:
    with pytest.raises(ValueError, match="graph_steps"):
        EvalCase.from_dict(
            {"id": "bad", "input": "x", "expect": {"graph_steps": ["agent", "tools"]}}
        )


def test_score_case_includes_graph_steps_only_when_pinned() -> None:
    good = _load("paris_fly_to.json")
    assert "graph_steps" not in score_case(PARIS_CASE, good).scores
    pinned = _case_with_steps(PARIS_STEPS)
    assert score_case(pinned, good).scores["graph_steps"].score == 1


# --- LLM-judge plumbing (stubbed, offline) -------------------------------------


def _stub_evaluator(verdict: bool, comment: str = "because") -> Any:
    def evaluator(*, inputs: str, outputs: str) -> dict[str, Any]:
        assert inputs and outputs  # the scorer must forward both
        return {"key": "final_answer_quality", "score": verdict, "comment": comment}

    return evaluator


def test_final_answer_scorer_passes_and_fails_on_verdict() -> None:
    good = _load("paris_fly_to.json")
    assert make_final_answer_scorer(_stub_evaluator(True))(PARIS_CASE, good).score == 1
    res = make_final_answer_scorer(_stub_evaluator(False, "made it up"))(PARIS_CASE, good)
    assert res.score == 0
    assert "made it up" in res.reason


def test_final_answer_scorer_fails_without_final_message() -> None:
    def explode(**_: Any) -> dict[str, Any]:
        raise AssertionError("judge must not be called without a final message")

    res = make_final_answer_scorer(explode)(PARIS_CASE, _traj([_ai(content="")]))
    assert res.score == 0
    assert "no final assistant message" in res.reason


# --- integration with score_case ----------------------------------------------


def test_score_case_includes_trajectory_match() -> None:
    report = score_case(PARIS_CASE, _load("paris_fly_to.json"))
    assert report.scores["trajectory_match"].score == 1
    assert "final_judge" not in report.scores  # no judge passed


def test_score_case_judges_only_keywordless_cases() -> None:
    judge = make_final_answer_scorer(_stub_evaluator(True))
    # area_of_polygon has no final_contains_any: the judge applies.
    area_case = CASES["area_of_polygon"]
    traj = _traj(
        [
            {"type": "human", "content": area_case.input},
            _ai([{"name": "area_of", "args": {"wkt": "POLYGON((0 0,0 1,1 1,1 0,0 0))"}}]),
            {"type": "tool", "content": '{"area_m2": 12308778361.469452}'},
            _ai(content="The polygon's area is about 12.3 billion square meters."),
        ]
    )
    report = score_case(area_case, traj, judge=judge)
    assert report.scores["final_judge"].score == 1
    assert report.passed, {k: v.reason for k, v in report.scores.items()}
    # geocode_then_fly_to_paris has keywords: the deterministic check owns it.
    report = score_case(PARIS_CASE, _load("paris_fly_to.json"), judge=judge)
    assert "final_judge" not in report.scores
