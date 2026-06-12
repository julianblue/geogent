"""Run the golden cases as a LangSmith experiment via ``aevaluate``.

This is the experimentation entry point that the pytest gate
(``test_evals.py``) deliberately isn't: concurrent case execution, repeated
runs for flake rates, model A/B via ``--model``, and hosted
experiment-over-experiment comparison. It reuses the whole existing pipeline —
the harness server bootstrap, the interrupt-resuming runner, and
``report.score_case`` with every scorer — so both entry points always grade
identically.

Requires LANGSMITH_API_KEY (experiment storage) and OPENROUTER_API_KEY (the
agent under test, and the judge unless ``--no-judge``). Typical runs::

    uv run python -m tests.evals.experiment
    uv run python -m tests.evals.experiment --model openrouter:anthropic/claude-sonnet-4-6 \\
        --repetitions 5 --concurrency 4 --experiment-prefix sonnet-baseline

The judge model is pinned independently of ``--model`` (via ``--judge-model``
or GEOGENT_EVAL_JUDGE_MODEL) so model comparisons aren't skewed by the judge
changing with the agent under test.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import Any

from tests.evals.agentevals_bridge import (
    FinalAnswerJudge,
    create_final_answer_judge,
    extract_graph_trajectory,
)
from tests.evals.dataset import EvalCase
from tests.evals.langsmith_dataset import DEFAULT_DATASET, sync_cases
from tests.evals.report import score_case
from tests.evals.runner import run_case
from tests.evals.scorers import final_assistant_text, tool_names
from tests.harness import DEFAULT_TEST_MODEL, backend_stub_server, langgraph_dev_server


def make_case(inputs: dict[str, Any], reference_outputs: dict[str, Any] | None = None) -> EvalCase:
    """Rebuild an :class:`EvalCase` from a LangSmith example's payloads.

    Inverse of ``langsmith_dataset.case_to_example`` (note the ``case_id`` ->
    ``id`` remap). The target only has inputs; evaluators pass the reference
    too so the golden ``expect`` block is restored.
    """
    ref = reference_outputs or {}
    return EvalCase.from_dict(
        {
            "id": inputs["case_id"],
            "input": inputs["input"],
            "configurable": inputs.get("configurable") or {},
            "expect": ref.get("expect") or {},
            "xfail": ref.get("xfail"),
        }
    )


def make_target(base_url: str) -> Any:
    """Async aevaluate target: one example in, one graded-able trajectory out."""

    async def run_geogent_case(inputs: dict[str, Any]) -> dict[str, Any]:
        state = await run_case(base_url, make_case(inputs))
        return {
            # Everything the evaluators grade...
            "trajectory": state,
            # ...plus condensed fields so experiment rows read well in the UI.
            "final_answer": final_assistant_text(state),
            "tool_calls": tool_names(state),
            "graph_trajectory": extract_graph_trajectory(state),
        }

    return run_geogent_case


def make_evaluator(judge: FinalAnswerJudge | None = None) -> Any:
    """One evaluator wrapping ``score_case`` so experiments and the pytest gate
    can never grade differently; each scorer becomes its own feedback key."""

    def geogent_scorers(
        inputs: dict[str, Any], outputs: dict[str, Any], reference_outputs: dict[str, Any]
    ) -> list[dict[str, Any]]:
        case = make_case(inputs, reference_outputs)
        report = score_case(case, outputs["trajectory"], judge=judge)
        feedback = [
            {"key": name, "score": res.score, "comment": res.reason}
            for name, res in report.scores.items()
        ]
        # xfail-aware verdict, mirroring what gates CI in the pytest suite.
        feedback.append(
            {"key": "gating_ok", "score": int(report.gating_ok), "comment": report.result}
        )
        return feedback

    return geogent_scorers


def default_experiment_judge_model() -> str:
    # Deliberately no TEST_AGENT_MODEL fallback (unlike the pytest suite's
    # default): in experiments the agent model varies, the judge must not.
    return os.getenv("GEOGENT_EVAL_JUDGE_MODEL") or DEFAULT_TEST_MODEL


async def run_experiment(args: argparse.Namespace) -> Any:
    from langsmith import Client, aevaluate

    client = Client()
    if not args.skip_sync:
        summary = sync_cases(client, args.dataset)
        print(f"[experiment] synced dataset {args.dataset!r}: {summary}")

    agent_model = args.model or os.getenv("TEST_AGENT_MODEL") or DEFAULT_TEST_MODEL
    judge_model = args.judge_model or default_experiment_judge_model()
    judge = create_final_answer_judge(judge_model) if args.judge else None

    with (
        backend_stub_server() as backend_url,
        langgraph_dev_server(
            backend_url,
            model=agent_model,
            # The dev server queues runs behind one worker job by default;
            # match it to client-side concurrency or "concurrent" runs serialize.
            n_jobs_per_worker=args.concurrency,
            log_name=".experiment_langgraph_dev.log",
        ) as base_url,
    ):
        results = await aevaluate(
            make_target(base_url),
            data=args.dataset,
            evaluators=[make_evaluator(judge)],
            max_concurrency=args.concurrency,
            num_repetitions=args.repetitions,
            experiment_prefix=args.experiment_prefix,
            metadata={
                "agent_model": agent_model,
                "judge_model": judge_model if args.judge else None,
                "repetitions": args.repetitions,
            },
            client=client,
        )
    print(f"[experiment] done: {results.experiment_name}")
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default=DEFAULT_DATASET, help="LangSmith dataset name")
    parser.add_argument("--model", default=None, help="agent model under test (AGENT_MODEL)")
    parser.add_argument(
        "--judge-model", default=None, help="judge model (default: GEOGENT_EVAL_JUDGE_MODEL)"
    )
    parser.add_argument(
        "--judge",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="grade keyword-less cases with the LLM judge (--no-judge to disable)",
    )
    parser.add_argument("--repetitions", type=int, default=1, help="runs per case")
    parser.add_argument("--concurrency", type=int, default=4, help="parallel case runs")
    parser.add_argument("--experiment-prefix", default=None)
    parser.add_argument(
        "--skip-sync", action="store_true", help="don't re-sync the YAML cases first"
    )
    args = parser.parse_args(argv)

    missing = [k for k in ("LANGSMITH_API_KEY", "OPENROUTER_API_KEY") if not os.getenv(k)]
    if missing:
        print(f"[experiment] missing required env: {', '.join(missing)}", file=sys.stderr)
        return 2

    asyncio.run(run_experiment(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
