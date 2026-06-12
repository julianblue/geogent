"""Sync the YAML golden cases into a LangSmith hosted dataset.

``cases/core.yaml`` stays the single source of truth; this module mirrors it
into a LangSmith dataset so ``experiment.py`` can run ``aevaluate`` over it
with hosted-experiment comparisons. Example ids are deterministic (uuid5 of
dataset name + case id), so re-syncing updates examples in place and
cross-experiment comparisons keep working after case edits.

Run it with::

    uv run python -m tests.evals.langsmith_dataset [--dataset NAME] [--dry-run]
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import yaml

from tests.evals.dataset import CASES_DIR, EvalCase

DEFAULT_DATASET = "geogent-evals-core"
DATASET_DESCRIPTION = (
    "Golden eval cases for the geogent agent, mirrored from "
    "apps/agent/tests/evals/cases/core.yaml — edit the YAML, then re-sync."
)

# Fixed namespace so example ids are stable across machines and runs.
_NAMESPACE = uuid.UUID("3f0c7c2e-9a1d-4d6b-8c70-5a3f5be1c5da")


def example_id(dataset_name: str, case_id: str) -> uuid.UUID:
    return uuid.uuid5(_NAMESPACE, f"{dataset_name}:{case_id}")


def load_raw_cases(path: Path | None = None) -> list[dict[str, Any]]:
    """Load cases as raw dicts (the typed loader has no ``to_dict``), but run
    each through ``EvalCase.from_dict`` so a malformed case still fails loudly
    before anything is pushed."""
    path = path or (CASES_DIR / "core.yaml")
    raw = yaml.safe_load(path.read_text()) or []
    if not isinstance(raw, list):
        raise ValueError(f"{path} must contain a YAML list of cases, got {type(raw).__name__}")
    for case in raw:
        EvalCase.from_dict(case)
    return raw


def case_to_example(dataset_name: str, raw_case: dict[str, Any]) -> dict[str, Any]:
    """Map one raw YAML case onto a LangSmith example payload.

    ``inputs`` hold what the target needs to run the case; ``outputs`` hold the
    golden reference (the raw ``expect`` block) the evaluators grade against.
    ``xfail`` rides along in outputs so evaluators can see it, and in metadata
    so the LangSmith UI can filter on it.
    """
    case_id = str(raw_case["id"])
    return {
        "id": example_id(dataset_name, case_id),
        "inputs": {
            "case_id": case_id,
            "input": raw_case["input"],
            "configurable": raw_case.get("configurable") or {},
        },
        "outputs": {
            "expect": raw_case.get("expect") or {},
            "xfail": raw_case.get("xfail"),
        },
        "metadata": {"case_id": case_id, "xfail": bool(raw_case.get("xfail"))},
    }


def sync_cases(
    client: Any,
    dataset_name: str = DEFAULT_DATASET,
    raw_cases: list[dict[str, Any]] | None = None,
) -> dict[str, int]:
    """Diff the YAML cases against the hosted dataset and reconcile.

    Create / update / delete by deterministic example id rather than wiping the
    dataset: recreating examples under the same ids after a delete can
    conflict, and in-place updates preserve experiment history.
    """
    raw_cases = load_raw_cases() if raw_cases is None else raw_cases
    if not client.has_dataset(dataset_name=dataset_name):
        client.create_dataset(dataset_name, description=DATASET_DESCRIPTION)

    desired = {
        str(ex["id"]): ex for ex in (case_to_example(dataset_name, c) for c in raw_cases)
    }
    existing = {str(ex.id): ex for ex in client.list_examples(dataset_name=dataset_name)}

    to_create = [ex for ex_id, ex in desired.items() if ex_id not in existing]
    to_update = [
        ex
        for ex_id, ex in desired.items()
        if ex_id in existing
        and (
            existing[ex_id].inputs != ex["inputs"]
            or existing[ex_id].outputs != ex["outputs"]
        )
    ]
    to_delete = [ex_id for ex_id in existing if ex_id not in desired]

    if to_create:
        client.create_examples(dataset_name=dataset_name, examples=to_create)
    if to_update:
        client.update_examples(dataset_name=dataset_name, updates=to_update)
    if to_delete:
        client.delete_examples(to_delete)

    return {
        "created": len(to_create),
        "updated": len(to_update),
        "deleted": len(to_delete),
        "unchanged": len(desired) - len(to_create) - len(to_update),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default=DEFAULT_DATASET, help="LangSmith dataset name")
    parser.add_argument("--cases", type=Path, default=None, help="case YAML (default core.yaml)")
    parser.add_argument(
        "--dry-run", action="store_true", help="validate and report; push nothing"
    )
    args = parser.parse_args(argv)

    raw_cases = load_raw_cases(args.cases)
    if args.dry_run:
        print(f"[sync] {len(raw_cases)} cases validate cleanly; dry run, nothing pushed")
        return 0

    if not os.getenv("LANGSMITH_API_KEY"):
        print("[sync] LANGSMITH_API_KEY is not set; cannot sync", file=sys.stderr)
        return 2

    from langsmith import Client

    summary = sync_cases(Client(), args.dataset, raw_cases)
    print(
        f"[sync] dataset {args.dataset!r}: "
        + ", ".join(f"{k}={v}" for k, v in summary.items())
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
