"""Fixtures shared by the live-LLM suites (e2e + evals).

These boot the real `langgraph dev` server in a subprocess and stand up a small
FastAPI stub for the backend so the agent's HTTP tools have something to talk
to. Both ``tests/e2e`` and ``tests/evals`` inherit them.

The ``langgraph_server`` fixture skips when ``OPENROUTER_API_KEY`` is unset, so
any test that depends on it is free to run on contributor machines and in CI
without a key. Offline tests (e.g. the scorer unit tests) don't depend on it
and run unconditionally.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
from collections.abc import Iterator

import pytest

from tests.harness import (
    AGENT_DIR,
    UvicornThread,
    build_backend_stub,
    free_port,
    wait_for,
)


@pytest.fixture(scope="session")
def backend_stub() -> Iterator[str]:
    port = free_port()
    app = build_backend_stub()
    thread = UvicornThread(app, port)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    wait_for(f"{base}/openapi.json", timeout=15.0)
    try:
        yield base
    finally:
        thread.stop()
        thread.join(timeout=5.0)


@pytest.fixture(scope="session")
def langgraph_server(backend_stub: str) -> Iterator[str]:
    """Spawn `langgraph dev` against the local agent directory."""
    if not os.getenv("OPENROUTER_API_KEY"):
        pytest.skip("OPENROUTER_API_KEY not set; skipping live LLM tests")

    port = free_port()
    env = os.environ.copy()
    env["BACKEND_URL"] = backend_stub
    env.setdefault(
        "AGENT_MODEL", os.getenv("TEST_AGENT_MODEL", "openrouter:anthropic/claude-3.5-sonnet")
    )
    # Disable LangSmith hooks so the test doesn't try to call out.
    env.setdefault("LANGSMITH_TRACING", "false")
    env.pop("LANGCHAIN_TRACING_V2", None)

    log_path = AGENT_DIR / ".pytest_langgraph_dev.log"
    log_file = log_path.open("w", buffering=1)
    proc = subprocess.Popen(  # noqa: S603 - intentional
        [
            sys.executable,
            "-m",
            "langgraph_cli",
            "dev",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-browser",
        ],
        cwd=AGENT_DIR,
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        wait_for(f"{base}/ok", timeout=90.0)
    except Exception:
        proc.terminate()
        with contextlib.suppress(Exception):
            proc.wait(timeout=5)
        raise
    try:
        yield base
    finally:
        proc.terminate()
        with contextlib.suppress(Exception):
            proc.wait(timeout=10)
        if proc.poll() is None:
            proc.kill()
        log_file.close()
