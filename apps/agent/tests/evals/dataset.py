"""Load and validate the in-repo eval dataset.

The dataset is a list of golden cases in ``cases/*.yaml``. This module turns the
raw YAML into typed :class:`EvalCase` objects and fails loudly on a malformed
file so a typo in a case never silently degrades into a skipped assertion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

CASES_DIR = Path(__file__).resolve().parent / "cases"


@dataclass(frozen=True)
class ArgConstraint:
    """A single argument expectation.

    Exactly one of ``between`` or ``equals`` is set. ``between`` is an inclusive
    numeric range ``[low, high]``; ``equals`` is an exact (numeric or string)
    match.
    """

    arg: str
    between: tuple[float, float] | None = None
    equals: Any = None

    @classmethod
    def from_spec(cls, arg: str, spec: dict[str, Any]) -> ArgConstraint:
        if not isinstance(spec, dict) or len(spec) != 1:
            raise ValueError(
                f"arg constraint for {arg!r} must be a single-key dict "
                f"(between|equals), got {spec!r}"
            )
        ((kind, value),) = spec.items()
        if kind == "between":
            if not (isinstance(value, list | tuple) and len(value) == 2):
                raise ValueError(f"'between' for {arg!r} must be [low, high], got {value!r}")
            return cls(arg=arg, between=(float(value[0]), float(value[1])))
        if kind == "equals":
            return cls(arg=arg, equals=value)
        raise ValueError(f"unknown arg constraint {kind!r} for {arg!r} (want between|equals)")


@dataclass(frozen=True)
class Expectation:
    tools_required: list[str] = field(default_factory=list)
    # tool name -> list of per-arg constraints
    args: dict[str, list[ArgConstraint]] = field(default_factory=dict)
    max_steps: int | None = None
    final_contains_any: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Expectation:
        args_raw = raw.get("args") or {}
        args: dict[str, list[ArgConstraint]] = {}
        for tool, arg_specs in args_raw.items():
            if not isinstance(arg_specs, dict):
                raise ValueError(f"args.{tool} must be a mapping of arg -> constraint")
            args[tool] = [ArgConstraint.from_spec(a, s) for a, s in arg_specs.items()]
        return cls(
            tools_required=list(raw.get("tools_required") or []),
            args=args,
            max_steps=raw.get("max_steps"),
            final_contains_any=list(raw.get("final_contains_any") or []),
        )


@dataclass(frozen=True)
class EvalCase:
    id: str
    input: str
    configurable: dict[str, Any]
    expect: Expectation

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> EvalCase:
        for key in ("id", "input"):
            if not raw.get(key):
                raise ValueError(f"case is missing required field {key!r}: {raw!r}")
        return cls(
            id=str(raw["id"]),
            input=str(raw["input"]),
            configurable=dict(raw.get("configurable") or {}),
            expect=Expectation.from_dict(raw.get("expect") or {}),
        )


def load_cases(path: Path | None = None) -> list[EvalCase]:
    """Load every case from a YAML file (defaults to ``cases/core.yaml``)."""
    path = path or (CASES_DIR / "core.yaml")
    raw = yaml.safe_load(path.read_text()) or []
    if not isinstance(raw, list):
        raise ValueError(f"{path} must contain a YAML list of cases, got {type(raw).__name__}")
    cases = [EvalCase.from_dict(c) for c in raw]
    ids = [c.id for c in cases]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"duplicate case ids in {path}: {sorted(dupes)}")
    return cases
