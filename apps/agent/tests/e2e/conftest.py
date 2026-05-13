"""Fixtures for the LangGraph e2e suite.

These tests boot the real `langgraph dev` server in a subprocess and stand up a
small FastAPI stub for the backend so the agent's HTTP tools have something
to talk to. The tests then drive the agent with a live LLM (OpenRouter) via
the LangGraph SDK.

The whole module is skipped when ``OPENROUTER_API_KEY`` is not set so the
suite remains free to run on contributor machines without keys.
"""

from __future__ import annotations

import contextlib
import os
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import uvicorn
from fastapi import FastAPI

AGENT_DIR = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for(url: str, timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    last: Exception | None = None
    while time.time() < deadline:
        try:
            r = httpx.get(url, timeout=2.0)
            if r.status_code < 500:
                return
        except Exception as exc:  # noqa: BLE001
            last = exc
        time.sleep(0.5)
    raise RuntimeError(f"timed out waiting for {url}: {last}")


def _build_backend_stub() -> FastAPI:
    """Mimic the geogent backend endpoints the agent's tools call.

    The shapes match `apps/backend` exactly so the LangChain tools deserialize
    cleanly; the values are canned so tests can assert on them.
    """
    app = FastAPI()
    state: dict[str, object] = {"features": []}

    @app.get("/api/v1/features")
    def list_features() -> list[dict]:
        return list(state["features"])  # type: ignore[arg-type]

    @app.post("/api/v1/analytics/buffer")
    def buffer(payload: dict) -> dict:
        wkt = payload.get("geometry_wkt", "")
        distance = payload.get("distance_m", 0)
        return {"buffered_wkt": f"BUFFERED({wkt}, {distance}m)"}

    @app.post("/api/v1/analytics/distance")
    def distance(_: dict) -> dict:
        return {"distance_m": 4123456.7}

    @app.post("/api/v1/analytics/area")
    def area(_: dict) -> dict:
        return {"area_m2": 12345.6}

    @app.post("/api/v1/analytics/intersects")
    def intersects(_: dict) -> dict:
        return {"intersects": True}

    @app.post("/api/v1/analytics/features-within")
    def features_within(_: dict) -> dict:
        # Deterministic fixture features the test asserts on by name.
        return {
            "features": [
                {"id": 101, "name": "Eiffel Tower"},
                {"id": 102, "name": "Louvre Museum"},
            ]
        }

    return app


class _UvicornThread(threading.Thread):
    def __init__(self, app: FastAPI, port: int) -> None:
        super().__init__(daemon=True)
        self.config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        self.server = uvicorn.Server(self.config)

    def run(self) -> None:  # pragma: no cover - thread target
        self.server.run()

    def stop(self) -> None:
        self.server.should_exit = True


@pytest.fixture(scope="session")
def backend_stub() -> Iterator[str]:
    port = _free_port()
    app = _build_backend_stub()
    thread = _UvicornThread(app, port)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    _wait_for(f"{base}/openapi.json", timeout=15.0)
    try:
        yield base
    finally:
        thread.stop()
        thread.join(timeout=5.0)


@pytest.fixture(scope="session")
def langgraph_server(backend_stub: str) -> Iterator[str]:
    """Spawn `langgraph dev` against the local agent directory."""
    if not os.getenv("OPENROUTER_API_KEY"):
        pytest.skip("OPENROUTER_API_KEY not set; skipping live LLM e2e tests")

    port = _free_port()
    env = os.environ.copy()
    env["BACKEND_URL"] = backend_stub
    env.setdefault("AGENT_MODEL", os.getenv("TEST_AGENT_MODEL", "openrouter:anthropic/claude-3.5-sonnet"))
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
        _wait_for(f"{base}/ok", timeout=90.0)
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


def _can_reach(url: str) -> bool:
    try:
        # Some sandboxes return 4xx with `x-deny-reason: host_not_allowed`
        # instead of a network error; treat any such response as unreachable.
        r = httpx.head(url, timeout=4.0, follow_redirects=True)
    except Exception:
        return False
    return r.headers.get("x-deny-reason") != "host_not_allowed"


@pytest.fixture(scope="session", autouse=True)
def _ensure_e2e_env() -> Iterator[None]:
    """Skip the whole module fast when there's no key or the LLM host is blocked."""
    if not os.getenv("OPENROUTER_API_KEY"):
        pytest.skip("OPENROUTER_API_KEY not set", allow_module_level=True)
    base = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    if not _can_reach(base):
        pytest.skip(
            f"OpenRouter host ({base}) unreachable from this environment; "
            "skipping live LLM e2e tests",
            allow_module_level=True,
        )
    yield
