"""Offline unit tests for the YAML -> LangSmith dataset sync.

No key needed: ``sync_cases`` is exercised against a stub client that records
calls, covering the create / update / delete / unchanged diff branches.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from tests.evals.langsmith_dataset import (
    case_to_example,
    example_id,
    load_raw_cases,
    sync_cases,
)

DATASET = "test-dataset"

RAW_CASE = {
    "id": "case_a",
    "input": "Do the thing.",
    "expect": {"tools_required": ["fly_to"], "max_steps": 4},
}


@dataclass
class _Example:
    id: Any
    inputs: dict[str, Any]
    outputs: dict[str, Any]


@dataclass
class StubClient:
    examples: list[_Example] = field(default_factory=list)
    datasets: set[str] = field(default_factory=set)
    created: list[dict] = field(default_factory=list)
    updated: list[dict] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)

    def has_dataset(self, *, dataset_name: str) -> bool:
        return dataset_name in self.datasets

    def create_dataset(self, dataset_name: str, *, description: str) -> None:
        self.datasets.add(dataset_name)

    def list_examples(self, *, dataset_name: str) -> list[_Example]:
        return list(self.examples)

    def create_examples(self, *, dataset_name: str, examples: list[dict]) -> None:
        self.created.extend(examples)

    def update_examples(self, *, dataset_name: str, updates: list[dict]) -> None:
        self.updated.extend(updates)

    def delete_examples(self, example_ids: list[str]) -> None:
        self.deleted.extend(example_ids)


def _existing(raw_case: dict[str, Any]) -> _Example:
    ex = case_to_example(DATASET, raw_case)
    return _Example(id=ex["id"], inputs=ex["inputs"], outputs=ex["outputs"])


def test_example_id_is_deterministic_and_dataset_scoped() -> None:
    assert example_id(DATASET, "case_a") == example_id(DATASET, "case_a")
    assert example_id(DATASET, "case_a") != example_id(DATASET, "case_b")
    assert example_id(DATASET, "case_a") != example_id("other", "case_a")


def test_case_to_example_shape() -> None:
    ex = case_to_example(DATASET, RAW_CASE)
    assert ex["inputs"] == {"case_id": "case_a", "input": "Do the thing.", "configurable": {}}
    assert ex["outputs"] == {"expect": RAW_CASE["expect"], "xfail": None}
    assert ex["metadata"] == {"case_id": "case_a", "xfail": False}


def test_sync_creates_dataset_and_examples_from_scratch() -> None:
    client = StubClient()
    summary = sync_cases(client, DATASET, [RAW_CASE])
    assert DATASET in client.datasets
    assert summary == {"created": 1, "updated": 0, "deleted": 0, "unchanged": 0}
    assert client.created[0]["inputs"]["case_id"] == "case_a"


def test_sync_diffs_update_delete_and_unchanged() -> None:
    case_b = {"id": "case_b", "input": "Other thing.", "expect": {}}
    stale = {"id": "case_gone", "input": "Old.", "expect": {}}
    client = StubClient(
        datasets={DATASET},
        examples=[_existing(RAW_CASE), _existing(case_b), _existing(stale)],
    )
    changed_a = {**RAW_CASE, "expect": {"tools_required": ["fly_to"], "max_steps": 9}}
    summary = sync_cases(client, DATASET, [changed_a, case_b])
    assert summary == {"created": 0, "updated": 1, "deleted": 1, "unchanged": 1}
    assert client.updated[0]["id"] == example_id(DATASET, "case_a")
    assert client.updated[0]["outputs"]["expect"]["max_steps"] == 9
    assert client.deleted == [str(example_id(DATASET, "case_gone"))]


def test_load_raw_cases_validates_via_typed_loader(tmp_path: Any) -> None:
    good = tmp_path / "good.yaml"
    good.write_text("- id: a\n  input: hi\n")
    assert load_raw_cases(good)[0]["id"] == "a"
    bad = tmp_path / "bad.yaml"
    bad.write_text("- input: missing id\n")
    with pytest.raises(ValueError, match="missing required field"):
        load_raw_cases(bad)


def test_load_raw_cases_round_trips_core_yaml() -> None:
    raw = load_raw_cases()
    assert {c["id"] for c in raw} >= {"geocode_then_fly_to_paris", "buffer_then_save_eiffel"}
