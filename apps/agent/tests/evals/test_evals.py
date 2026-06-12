"""Live eval: drive the real agent over the dataset and grade each trajectory.

Marked ``eval`` and gated on the ``langgraph_server`` fixture, so it skips
without ``OPENROUTER_API_KEY`` exactly like the e2e suite. The offline scorer
guarantees live in ``test_scorers.py`` / ``test_agentevals_bridge.py`` and run
with no key.

Each case is graded by the four deterministic scorers, agentevals' trajectory
match, and — on cases without keyword expectations — an openevals LLM judge of
final-answer quality (model via ``GEOGENT_EVAL_JUDGE_MODEL``).

Per-case tests carry ``@pytest.mark.langsmith``: with ``LANGSMITH_API_KEY``
set, a run logs a LangSmith experiment (one row per case, every scorer
attached as feedback; suite name via ``LANGSMITH_TEST_SUITE``). Without a key
we force ``LANGSMITH_TEST_TRACKING=false`` so the plugin and all ``t.log_*``
calls degrade to no-ops and the suite behaves as plain pytest.

Run it with::

    uv run pytest -m eval -s                          # -s to see the score table
    LANGSMITH_API_KEY=... uv run pytest -m eval -s    # also logs an experiment
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from langsmith import testing as t

from tests.evals.agentevals_bridge import (
    FinalAnswerJudge,
    create_final_answer_judge,
    extract_graph_trajectory,
)
from tests.evals.dataset import EvalCase, load_cases
from tests.evals.report import CaseReport, build_report, maybe_push_to_langsmith, render_table
from tests.evals.runner import run_case
from tests.evals.scorers import final_assistant_text, tool_names
from tests.harness import can_reach

# Degrade gracefully when LangSmith isn't configured: without this, the
# @pytest.mark.langsmith wrapper would try (and fail) to reach the API.
if not os.getenv("LANGSMITH_API_KEY"):
    os.environ.setdefault("LANGSMITH_TEST_TRACKING", "false")

pytestmark = pytest.mark.eval

CASES = load_cases()


@pytest.fixture(scope="module", autouse=True)
def _ensure_eval_env() -> None:
    if not os.getenv("OPENROUTER_API_KEY"):
        pytest.skip("OPENROUTER_API_KEY not set", allow_module_level=True)
    base = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    if not can_reach(base):
        pytest.skip(
            f"OpenRouter host ({base}) unreachable; skipping live eval",
            allow_module_level=True,
        )


RECORDINGS_DIR = Path(__file__).resolve().parent / "recordings"


@pytest.fixture(scope="module")
async def trajectories(langgraph_server: str) -> dict[str, dict[str, Any]]:
    """Run every case once against the live server; share the trajectories.

    With ``GEOGENT_EVAL_RECORD=1``, each raw trajectory is also written to
    ``recordings/<case_id>.json``; ``test_replay.py`` re-scores committed
    recordings offline, so scorer and case changes get regression coverage
    without a key.
    """
    out: dict[str, dict[str, Any]] = {}
    for case in CASES:
        out[case.id] = await run_case(langgraph_server, case)
    if os.getenv("GEOGENT_EVAL_RECORD"):
        RECORDINGS_DIR.mkdir(exist_ok=True)
        for case_id, state in out.items():
            path = RECORDINGS_DIR / f"{case_id}.json"
            path.write_text(json.dumps(state, indent=2, default=str) + "\n")
        print(f"\n[evals] recorded {len(out)} trajectories to {RECORDINGS_DIR}")
    return out


@pytest.fixture(scope="module")
def judge() -> FinalAnswerJudge:
    """LLM-as-judge over OpenRouter; safe to build here since the module
    already skipped without OPENROUTER_API_KEY."""
    return create_final_answer_judge()


@pytest.fixture(scope="module")
def reports(
    trajectories: dict[str, dict[str, Any]], judge: FinalAnswerJudge
) -> dict[str, CaseReport]:
    """Score every case exactly once (the judge bills per call), print the
    table, and share the reports with the per-case tests."""
    pairs = [(c, trajectories[c.id]) for c in CASES]
    built = build_report(pairs, judge=judge)
    table = render_table(built)
    print("\n" + table + "\n")
    maybe_push_to_langsmith(built)
    return {r.case_id: r for r in built}


@pytest.mark.langsmith
@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_case(
    case: EvalCase,
    trajectories: dict[str, dict[str, Any]],
    reports: dict[str, CaseReport],
) -> None:
    trajectory = trajectories[case.id]
    report = reports[case.id]

    # Override the auto-captured inputs (which would include whole fixtures)
    # and attach every scorer as experiment feedback. All no-ops offline.
    t.log_inputs({"case_id": case.id, "input": case.input})
    t.log_outputs(
        {
            "final_answer": final_assistant_text(trajectory),
            "tool_calls": tool_names(trajectory),
            "graph_trajectory": extract_graph_trajectory(trajectory),
        }
    )
    for name, res in report.scores.items():
        t.log_feedback(key=name, score=res.score, comment=res.reason)

    failures = [f"{name}: {res.reason}" for name, res in report.scores.items() if not res]
    if case.xfail and failures:
        pytest.xfail(f"{case.xfail}: {failures}")
    assert not failures, f"{case.id} failed scorers:\n  " + "\n  ".join(failures)


def test_overall(reports: dict[str, CaseReport]) -> None:
    """Print the table (via the reports fixture) and require every non-xfail case to pass."""
    failed = [cid for cid, r in reports.items() if not r.gating_ok]
    assert not failed, f"cases failed: {failed}"
