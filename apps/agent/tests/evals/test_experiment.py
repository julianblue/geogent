"""Offline unit tests for the aevaluate experiment wiring.

No key needed: the case round-trip and the score_case-backed evaluator are
pure given a trajectory, and the judge is stubbed where involved.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests.evals.agentevals_bridge import make_final_answer_scorer
from tests.evals.dataset import load_cases
from tests.evals.experiment import make_case, make_evaluator
from tests.evals.langsmith_dataset import DEFAULT_DATASET, case_to_example, load_raw_cases

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())


def test_make_case_round_trips_every_example() -> None:
    """YAML -> example payloads -> EvalCase must equal YAML -> EvalCase."""
    by_id = {c.id: c for c in load_cases()}
    for raw in load_raw_cases():
        ex = case_to_example(DEFAULT_DATASET, raw)
        rebuilt = make_case(ex["inputs"], ex["outputs"])
        assert rebuilt == by_id[rebuilt.id]


def _example_for(case_id: str) -> dict[str, Any]:
    raw = next(c for c in load_raw_cases() if c["id"] == case_id)
    return case_to_example(DEFAULT_DATASET, raw)


def test_evaluator_emits_every_scorer_plus_gating() -> None:
    ex = _example_for("geocode_then_fly_to_paris")
    feedback = make_evaluator()(
        inputs=ex["inputs"],
        outputs={"trajectory": _load("paris_fly_to.json")},
        reference_outputs=ex["outputs"],
    )
    by_key = {f["key"]: f for f in feedback}
    assert set(by_key) == {"tool_selection", "args", "length", "final", "trajectory_match", "gating_ok"}
    assert all(f["score"] == 1 for f in feedback), by_key
    assert by_key["gating_ok"]["comment"] == "PASS"


def test_evaluator_gating_tolerates_xfail_cases() -> None:
    # An xfail-marked case with a failing trajectory: scorers fail but
    # gating_ok stays 1, mirroring the live suite's xfail behavior. The xfail
    # is injected here so the test doesn't depend on the live dataset
    # currently containing a known-weak case.
    raw = dict(next(c for c in load_raw_cases() if c["id"] == "buffer_then_save_eiffel"))
    raw["xfail"] = "injected: known-weak case for gating test"
    ex = case_to_example(DEFAULT_DATASET, raw)
    feedback = make_evaluator()(
        inputs=ex["inputs"],
        outputs={"trajectory": _load("paris_fly_to_bad.json")},
        reference_outputs=ex["outputs"],
    )
    by_key = {f["key"]: f for f in feedback}
    assert by_key["tool_selection"]["score"] == 0
    assert by_key["gating_ok"]["score"] == 1
    assert by_key["gating_ok"]["comment"] == "XFAIL"


def test_evaluator_runs_stub_judge_on_keywordless_cases() -> None:
    ex = _example_for("buffer_explicit_point")  # no final_contains_any
    traj = {
        "values": {
            "messages": [
                {"type": "human", "content": ex["inputs"]["input"]},
                {
                    "type": "ai",
                    "content": "",
                    "tool_calls": [{"name": "buffer_geometry", "args": {"distance_m": 1000}}],
                },
                {"type": "tool", "content": '{"buffered_wkt": "BUFFERED(...)"}'},
                {"type": "ai", "content": "Here is the 1000 m buffer geometry: BUFFERED(...)"},
            ]
        }
    }
    judge = make_final_answer_scorer(
        lambda **kw: {"key": "final_answer_quality", "score": True, "comment": "concrete"}
    )
    feedback = make_evaluator(judge)(
        inputs=ex["inputs"], outputs={"trajectory": traj}, reference_outputs=ex["outputs"]
    )
    by_key = {f["key"]: f for f in feedback}
    assert by_key["final_judge"]["score"] == 1
    assert "concrete" in by_key["final_judge"]["comment"]
