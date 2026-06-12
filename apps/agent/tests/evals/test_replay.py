"""Offline replay: re-score committed live trajectories against the cases.

The recordings in ``recordings/`` are raw ``threads.get_state`` snapshots
captured by running the live suite with ``GEOGENT_EVAL_RECORD=1``. Replaying
them through ``score_case`` (deterministic scorers only — no judge) gives the
scorers and ``core.yaml`` expectations regression coverage with no key and no
network: if an expectation or scorer change would break a known-good live run,
this catches it in `make test`.

A recording is graded with the same xfail tolerance as the live gate
(``gating_ok``), so a committed trajectory of a known-weak case may fail
scorers without failing here. Stale recordings (no matching case id) skip with
a pointed reason rather than silently passing — delete or re-record them.

Refresh the recordings with::

    GEOGENT_EVAL_RECORD=1 uv run pytest -m eval
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.evals.dataset import load_cases
from tests.evals.report import score_case

RECORDINGS_DIR = Path(__file__).resolve().parent / "recordings"
RECORDINGS = sorted(RECORDINGS_DIR.glob("*.json")) if RECORDINGS_DIR.is_dir() else []
CASES = {c.id: c for c in load_cases()}

if not RECORDINGS:
    pytest.skip(
        "no committed recordings; run the live suite with GEOGENT_EVAL_RECORD=1",
        allow_module_level=True,
    )


@pytest.mark.parametrize("path", RECORDINGS, ids=lambda p: p.stem)
def test_recording_still_gates_green(path: Path) -> None:
    case = CASES.get(path.stem)
    if case is None:
        pytest.skip(f"stale recording {path.name}: no case with id {path.stem!r} in core.yaml")
    report = score_case(case, json.loads(path.read_text()))
    failures = [f"{name}: {res.reason}" for name, res in report.scores.items() if not res]
    assert report.gating_ok, (
        f"recorded trajectory for {case.id} no longer passes its scorers:\n  "
        + "\n  ".join(failures)
    )


def test_every_case_has_a_recording() -> None:
    """Soft inventory check: flag cases without a recording so coverage gaps
    are visible, but don't fail CI over them (new cases land before keys)."""
    missing = sorted(set(CASES) - {p.stem for p in RECORDINGS})
    if missing:
        pytest.skip(f"cases without recordings (re-record when convenient): {missing}")
