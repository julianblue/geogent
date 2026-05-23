"""E2E-only fixtures.

The shared ``backend_stub`` and ``langgraph_server`` fixtures now live in
``tests/conftest.py`` so the evals suite can reuse them. What's left here is the
e2e-specific guard: skip the whole module fast when there's no key or the LLM
host is blocked, before any server is spawned.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from tests.harness import can_reach


@pytest.fixture(scope="session", autouse=True)
def _ensure_e2e_env() -> Iterator[None]:
    """Skip the whole module fast when there's no key or the LLM host is blocked."""
    if not os.getenv("OPENROUTER_API_KEY"):
        pytest.skip("OPENROUTER_API_KEY not set", allow_module_level=True)
    base = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    if not can_reach(base):
        pytest.skip(
            f"OpenRouter host ({base}) unreachable from this environment; "
            "skipping live LLM e2e tests",
            allow_module_level=True,
        )
    yield
