"""Live eval: drive the real agent over the dataset and grade each trajectory.

Marked ``eval`` and gated on the ``langgraph_server`` fixture, so it skips
without ``OPENROUTER_API_KEY`` exactly like the e2e suite. The offline scorer
guarantees live in ``test_scorers.py`` and run with no key.

Run it with::

    uv run pytest -m eval -s        # -s to see the score table
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from tests.evals.dataset import load_cases
from tests.evals.report import build_report, maybe_push_to_langsmith, render_table, score_case
from tests.evals.runner import run_case
from tests.harness import can_reach

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


@pytest.fixture(scope="module")
async def trajectories(langgraph_server: str) -> dict[str, dict[str, Any]]:
    """Run every case once against the live server; share the trajectories."""
    out: dict[str, dict[str, Any]] = {}
    for case in CASES:
        out[case.id] = await run_case(langgraph_server, case)
    return out


@pytest.fixture(scope="module")
def reports(trajectories: dict[str, dict[str, Any]]) -> dict[str, Any]:
    pairs = [(c, trajectories[c.id]) for c in CASES]
    built = build_report(pairs)
    table = render_table(built)
    print("\n" + table + "\n")
    maybe_push_to_langsmith(built)
    return {r.case_id: r for r in built}


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_case(case: Any, trajectories: dict[str, dict[str, Any]]) -> None:
    report = score_case(case, trajectories[case.id])
    failures = [f"{name}: {res.reason}" for name, res in report.scores.items() if not res]
    if case.xfail and failures:
        pytest.xfail(f"{case.xfail}: {failures}")
    assert not failures, f"{case.id} failed scorers:\n  " + "\n  ".join(failures)


def test_overall(reports: dict[str, Any]) -> None:
    """Print the table (via the reports fixture) and require every non-xfail case to pass."""
    failed = [cid for cid, r in reports.items() if not r.gating_ok]
    assert not failed, f"cases failed: {failed}"
