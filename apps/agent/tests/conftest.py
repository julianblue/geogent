"""Fixtures shared by the live-LLM suites (e2e + evals).

These boot the real `langgraph dev` server in a subprocess and stand up a small
FastAPI stub for the backend so the agent's HTTP tools have something to talk
to. Both ``tests/e2e`` and ``tests/evals`` inherit them. The actual server
bootstrap lives in pytest-free context managers in ``tests/harness.py`` so the
experiment CLI (``tests/evals/experiment.py``) can reuse it.

The ``langgraph_server`` fixture skips when ``OPENROUTER_API_KEY`` is unset, so
any test that depends on it is free to run on contributor machines and in CI
without a key. Offline tests (e.g. the scorer unit tests) don't depend on it
and run unconditionally.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from tests.harness import backend_stub_server, langgraph_dev_server


@pytest.fixture(scope="session")
def backend_stub() -> Iterator[str]:
    with backend_stub_server() as base:
        yield base


@pytest.fixture(scope="session")
def langgraph_server(backend_stub: str) -> Iterator[str]:
    """Spawn `langgraph dev` against the local agent directory."""
    if not os.getenv("OPENROUTER_API_KEY"):
        pytest.skip("OPENROUTER_API_KEY not set; skipping live LLM tests")
    with langgraph_dev_server(backend_stub, log_name=".pytest_langgraph_dev.log") as base:
        yield base
