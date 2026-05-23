"""Offline tests for the dataset loader + the committed core.yaml.

Runs with no key. Guarantees the shipped dataset stays loadable and well-formed
(so a typo in a case fails CI here rather than silently in a live run).
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tests.evals.dataset import EvalCase, load_cases


def test_core_yaml_loads_and_is_nonempty() -> None:
    cases = load_cases()
    assert cases, "core.yaml produced no cases"
    assert all(isinstance(c, EvalCase) for c in cases)
    assert all(c.id and c.input for c in cases)


def test_core_yaml_ids_unique() -> None:
    ids = [c.id for c in load_cases()]
    assert len(ids) == len(set(ids))


def test_paris_case_parsed_with_constraints() -> None:
    paris = next(c for c in load_cases() if c.id == "geocode_then_fly_to_paris")
    assert paris.expect.tools_required == ["geocode_place"]
    assert paris.expect.max_steps == 6
    fly_to = {c.arg: c for c in paris.expect.args["fly_to"]}
    assert fly_to["longitude"].between == (1.5, 3.5)


def test_duplicate_ids_rejected(tmp_path: Path) -> None:
    p = tmp_path / "dupe.yaml"
    p.write_text(
        textwrap.dedent(
            """
            - id: a
              input: hi
            - id: a
              input: yo
            """
        )
    )
    with pytest.raises(ValueError, match="duplicate case ids"):
        load_cases(p)


def test_bad_arg_constraint_rejected(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text(
        textwrap.dedent(
            """
            - id: a
              input: hi
              expect:
                args:
                  fly_to:
                    longitude: {nonsense: [1, 2]}
            """
        )
    )
    with pytest.raises(ValueError, match="unknown arg constraint"):
        load_cases(p)
