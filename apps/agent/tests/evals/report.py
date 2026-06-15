"""Aggregate per-case scores into a report; optionally push to LangSmith.

``score_case`` applies every scorer to one (case, trajectory) pair: the four
deterministic ones, agentevals' trajectory match, and — when a ``judge`` is
passed and the case has no keyword expectation — the LLM final-answer judge.
``build_report`` collects many of those. ``render_table`` formats a plain-text
table for the console / CI logs. ``maybe_push_to_langsmith`` is a no-op unless
``LANGSMITH_API_KEY`` is set, so importing and calling it is always safe.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from tests.evals.agentevals_bridge import (
    FinalAnswerJudge,
    score_graph_steps,
    score_trajectory_match,
)
from tests.evals.dataset import EvalCase
from tests.evals.scorers import (
    ScoreResult,
    score_argument_correctness,
    score_final_answer,
    score_tool_selection,
    score_tools_forbidden,
    score_trajectory_length,
)

SCORER_NAMES = (
    "tool_selection",
    "tools_forbidden",
    "args",
    "length",
    "final",
    "trajectory_match",
    "graph_steps",
    "final_judge",
)


@dataclass(frozen=True)
class CaseReport:
    case_id: str
    scores: dict[str, ScoreResult]
    xfail: str | None = None  # known-weakness reason, if any

    @property
    def passed(self) -> bool:
        return all(s.score == 1 for s in self.scores.values())

    @property
    def gating_ok(self) -> bool:
        """Whether this case should keep CI green (a passing case, or a failing
        but expected-to-fail one)."""
        return self.passed or self.xfail is not None

    @property
    def result(self) -> str:
        if self.xfail is not None:
            return "XPASS" if self.passed else "XFAIL"
        return "PASS" if self.passed else "FAIL"

    @property
    def total(self) -> int:
        return sum(s.score for s in self.scores.values())


def score_case(
    case: EvalCase, trajectory: dict[str, Any], *, judge: FinalAnswerJudge | None = None
) -> CaseReport:
    e = case.expect
    scores = {
        "tool_selection": score_tool_selection(trajectory, e.tools_required),
        "args": score_argument_correctness(trajectory, e.args),
        "length": score_trajectory_length(trajectory, e.max_steps),
        "final": score_final_answer(trajectory, e.final_contains_any),
        "trajectory_match": score_trajectory_match(trajectory, case),
    }
    # Only scored when a case sets it, so cases without a guardrail keep their
    # original scorer set (and the "fails every scorer" fixtures stay all-zero).
    if e.tools_forbidden:
        scores["tools_forbidden"] = score_tools_forbidden(trajectory, e.tools_forbidden)
    if e.graph_steps is not None:
        scores["graph_steps"] = score_graph_steps(trajectory, case)
    # The judge covers exactly the gap the deterministic final check leaves:
    # cases whose free-form output has no stable keyword to assert on.
    if judge is not None and not e.final_contains_any:
        scores["final_judge"] = judge(case, trajectory)
    return CaseReport(case_id=case.id, scores=scores, xfail=case.xfail)


def build_report(
    pairs: list[tuple[EvalCase, dict[str, Any]]], *, judge: FinalAnswerJudge | None = None
) -> list[CaseReport]:
    return [score_case(case, traj, judge=judge) for case, traj in pairs]


def render_table(reports: list[CaseReport]) -> str:
    """Render a per-case + overall pass/fail table as monospace text.

    A ``-`` cell means the scorer didn't apply to that case (e.g. the LLM
    judge on a case with deterministic keywords, or with no judge configured).
    """
    id_w = max([len("case")] + [len(r.case_id) for r in reports], default=4)
    names = [n for n in SCORER_NAMES if any(n in r.scores for r in reports)]
    widths = [max(len(n), 4) for n in names]
    header = (
        f"{'case':<{id_w}}  "
        + "  ".join(f"{n:>{w}}" for n, w in zip(names, widths, strict=True))
        + "  result"
    )
    lines = [header, "-" * len(header)]
    for r in reports:
        cells = "  ".join(
            f"{('-' if r.scores.get(n) is None else 'PASS' if r.scores[n].score else 'FAIL'):>{w}}"
            for n, w in zip(names, widths, strict=True)
        )
        lines.append(f"{r.case_id:<{id_w}}  {cells}  {r.result}")

    passed = sum(1 for r in reports if r.passed)
    xfailed = sum(1 for r in reports if r.xfail is not None and not r.passed)
    total_checks = sum(len(r.scores) for r in reports)
    passed_checks = sum(r.total for r in reports)
    lines.append("-" * len(header))
    suffix = f"   ({xfailed} xfail)" if xfailed else ""
    lines.append(
        f"cases: {passed}/{len(reports)} passed   "
        f"checks: {passed_checks}/{total_checks} passed{suffix}"
    )
    return "\n".join(lines)


def maybe_push_to_langsmith(reports: list[CaseReport], *, project: str | None = None) -> bool:
    """Push per-check scores to LangSmith as feedback. No-op without a key.

    Returns ``True`` if a push was attempted. We import lazily and swallow any
    client error into a printed warning so a flaky LangSmith never fails a run
    whose real job is to score trajectories.
    """
    if not os.getenv("LANGSMITH_API_KEY"):
        return False
    try:
        from datetime import UTC, datetime
        from uuid import uuid4

        from langsmith import Client

        client = Client()
        proj = project or os.getenv("LANGSMITH_PROJECT", "geogent-evals")
        for r in reports:
            # create_run() returns None, so we mint the id ourselves and reuse
            # it for feedback; otherwise the scores would never be attached.
            run_id = uuid4()
            now = datetime.now(UTC)
            client.create_run(
                id=run_id,
                name=f"eval:{r.case_id}",
                run_type="chain",
                inputs={"case_id": r.case_id},
                outputs={n: s.score for n, s in r.scores.items()},
                start_time=now,
                end_time=now,
                project_name=proj,
            )
            for name, result in r.scores.items():
                client.create_feedback(run_id, key=name, score=result.score, comment=result.reason)
    except Exception as exc:  # noqa: BLE001 - never fail the eval on telemetry
        print(f"[evals] LangSmith push skipped: {exc}")
    return True
