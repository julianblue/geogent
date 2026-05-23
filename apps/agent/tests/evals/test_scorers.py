"""Offline unit tests for the four scorers.

These run with NO API key: every scorer consumes a canned trajectory dict (the
shape ``threads.get_state`` returns). ``paris_fly_to.json`` is a real trajectory
captured from a live OpenRouter run (it passes) and ``paris_fly_to_bad.json`` a
hand-authored failing one, giving one pass + one fail per scorer against the
``geocode_then_fly_to_paris`` golden case; inline trajectories cover the any-of,
equals, and empty-constraint branches.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests.evals.dataset import ArgConstraint, load_cases
from tests.evals.report import score_case
from tests.evals.scorers import (
    count_steps,
    score_argument_correctness,
    score_final_answer,
    score_tool_selection,
    score_trajectory_length,
    tool_names,
)

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


PARIS_CASE = next(c for c in load_cases() if c.id == "geocode_then_fly_to_paris")


# --- full-pipeline pass/fail over recorded fixtures --------------------------


def test_recorded_good_trajectory_passes_every_scorer() -> None:
    report = score_case(PARIS_CASE, _load("paris_fly_to.json"))
    assert report.passed, {k: v.reason for k, v in report.scores.items()}


def test_recorded_bad_trajectory_fails_every_scorer() -> None:
    report = score_case(PARIS_CASE, _load("paris_fly_to_bad.json"))
    assert not report.passed
    assert all(s.score == 0 for s in report.scores.values()), {
        k: v.reason for k, v in report.scores.items()
    }


# --- tool selection ----------------------------------------------------------


def test_tool_selection_pass_and_fail() -> None:
    good = _load("paris_fly_to.json")
    assert score_tool_selection(good, ["geocode_place"]).score == 1
    assert score_tool_selection(good, ["features_within"]).score == 0


def test_tool_selection_any_of_group() -> None:
    traj = _traj([_ai([{"name": "add_buffer_layer", "args": {"distance_meters": 500}}])])
    assert score_tool_selection(traj, [["buffer_geometry", "add_buffer_layer"]]).score == 1
    assert score_tool_selection(traj, [["features_within", "list_features"]]).score == 0


def test_tool_selection_empty_is_pass() -> None:
    assert score_tool_selection(_traj([]), []).score == 1


# --- argument correctness ----------------------------------------------------


def test_args_between_pass_and_fail() -> None:
    good = _load("paris_fly_to.json")
    ok = score_argument_correctness(
        good, {"fly_to": [ArgConstraint("longitude", between=(1.5, 3.5))]}
    )
    assert ok.score == 1, ok.reason
    bad = score_argument_correctness(
        good, {"fly_to": [ArgConstraint("longitude", between=(10.0, 20.0))]}
    )
    assert bad.score == 0, bad.reason


def test_args_equals_pass_and_fail() -> None:
    traj = _traj([_ai([{"name": "buffer_geometry", "args": {"distance_m": 1000}}])])
    assert (
        score_argument_correctness(
            traj, {"buffer_geometry": [ArgConstraint("distance_m", equals=1000)]}
        ).score
        == 1
    )
    assert (
        score_argument_correctness(
            traj, {"buffer_geometry": [ArgConstraint("distance_m", equals=500)]}
        ).score
        == 0
    )


def test_args_uncalled_tool_fails() -> None:
    res = score_argument_correctness(_traj([]), {"fly_to": [ArgConstraint("longitude", equals=1)]})
    assert res.score == 0
    assert "never called" in res.reason


def test_args_picks_satisfying_invocation() -> None:
    # First fly_to is wrong, second is right: any single satisfying call passes.
    traj = _traj(
        [
            _ai([{"name": "fly_to", "args": {"latitude": 0.0}}]),
            _ai([{"name": "fly_to", "args": {"latitude": 48.9}}]),
        ]
    )
    assert (
        score_argument_correctness(
            traj, {"fly_to": [ArgConstraint("latitude", between=(48.0, 49.5))]}
        ).score
        == 1
    )


# --- trajectory length -------------------------------------------------------


def test_length_pass_and_fail() -> None:
    good = _load("paris_fly_to.json")
    assert count_steps(good) == 3
    assert score_trajectory_length(good, 6).score == 1
    assert score_trajectory_length(good, 2).score == 0


def test_length_no_constraint_is_pass() -> None:
    assert score_trajectory_length(_load("paris_fly_to_bad.json"), None).score == 1


# --- final answer ------------------------------------------------------------


def test_final_pass_and_fail() -> None:
    good = _load("paris_fly_to.json")
    assert score_final_answer(good, ["paris"]).score == 1
    assert score_final_answer(good, ["tokyo"]).score == 0


def test_final_empty_keywords_requires_message() -> None:
    assert score_final_answer(_load("paris_fly_to.json"), []).score == 1
    assert score_final_answer(_traj([_ai(content="")]), []).score == 0


def test_final_judge_hook_overrides_substring() -> None:
    good = _load("paris_fly_to.json")
    # Substring would fail on "tokyo", but the judge hook forces a verdict.
    assert score_final_answer(good, ["tokyo"], judge=lambda text, kw: True).score == 1
    assert score_final_answer(good, ["paris"], judge=lambda text, kw: False).score == 0


# --- extraction helpers sanity ----------------------------------------------


def test_tool_names_order_preserved() -> None:
    assert tool_names(_load("paris_fly_to.json")) == ["geocode_place", "fly_to"]
