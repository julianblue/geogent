"""Shared test harness helpers for the live-LLM suites (e2e + evals).

Both suites need the same plumbing: a free port, a readiness poll, a FastAPI
stub mimicking the geogent backend, and a thread that serves it. These live
here as plain importable functions so ``tests/conftest.py`` can expose them as
fixtures and ``tests/e2e/conftest.py`` can reuse the reachability probe without
duplicating code.
"""

from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI

# tests/harness.py -> tests/ -> apps/agent
AGENT_DIR = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for(url: str, timeout: float = 60.0) -> None:
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


def can_reach(url: str) -> bool:
    try:
        # Some sandboxes return 4xx with `x-deny-reason: host_not_allowed`
        # instead of a network error; treat any such response as unreachable.
        r = httpx.head(url, timeout=4.0, follow_redirects=True)
    except Exception:
        return False
    return r.headers.get("x-deny-reason") != "host_not_allowed"


def build_backend_stub() -> FastAPI:
    """Mimic the geogent backend endpoints the agent's tools call.

    The shapes match `apps/backend` exactly so the LangChain tools deserialize
    cleanly; the values are canned so tests can assert on them.
    """
    app = FastAPI()
    state: dict[str, object] = {"features": [], "time_series_polls": {}}

    @app.post("/api/v1/auth/login")
    def login(_: dict) -> dict:
        # The agent's backend_client authenticates before every call; mirror the
        # real backend's TokenResponse shape so the auth flow gets a bearer token.
        return {"access_token": "stub-token", "token_type": "bearer", "expires_in": 3600}

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
        # Deterministic fixture features the tests assert on by name.
        return {
            "features": [
                {"id": 101, "name": "Eiffel Tower"},
                {"id": 102, "name": "Louvre Museum"},
            ]
        }

    @app.post("/api/v1/analytics/zonal-stats")
    def zonal_stats(payload: dict) -> dict:
        field_id = int(payload.get("field_id", 1))
        index = payload.get("index", "ndvi")
        return {
            "field_id": field_id,
            "index": index,
            "scene": {
                "id": "S2B_31UDQ_20260501_0_L2A",
                "datetime": "2026-05-01T10:30:00Z",
                "cloud_cover": 4.2,
                "epsg": 32631,
            },
            "stats": {
                "mean": 0.63,
                "min": 0.11,
                "max": 0.92,
                "std": 0.17,
                "valid_pixels": 12034,
                "nodata_pixels": 321,
            },
            "histogram": {
                "bin_edges": [-1.0, -0.5, 0.0, 0.5, 1.0],
                "counts": [12, 211, 3490, 8321],
            },
            "cached": True,
        }

    @app.post("/api/v1/analytics/time-series", status_code=202)
    def start_time_series(_: dict) -> dict:
        job_id = "11111111-1111-1111-1111-111111111111"
        polls: dict[str, int] = state["time_series_polls"]  # type: ignore[assignment]
        polls[job_id] = 0
        return {"job_id": job_id, "status": "pending"}

    @app.get("/api/v1/analytics/time-series/{job_id}")
    def get_time_series(job_id: str) -> dict:
        polls: dict[str, int] = state["time_series_polls"]  # type: ignore[assignment]
        polls[job_id] = polls.get(job_id, 0) + 1
        if polls[job_id] == 1:
            return {
                "job_id": job_id,
                "status": "running",
                "field_id": 7,
                "index": "ndvi",
                "params": {},
                "points": [],
                "error": None,
            }
        return {
            "job_id": job_id,
            "status": "succeeded",
            "field_id": 7,
            "index": "ndvi",
            "params": {"start_date": "2025-04-01", "end_date": "2025-09-30"},
            "points": [
                {
                    "scene_id": "S2A_31UDQ_20250412_0_L2A",
                    "datetime": "2025-04-12T10:30:00Z",
                    "cloud_cover": 6.1,
                    "mean": 0.51,
                    "min": 0.15,
                    "max": 0.81,
                    "std": 0.12,
                    "valid_pixels": 11700,
                },
                {
                    "scene_id": "S2B_31UDQ_20250920_0_L2A",
                    "datetime": "2025-09-20T10:30:00Z",
                    "cloud_cover": 3.8,
                    "mean": 0.68,
                    "min": 0.2,
                    "max": 0.9,
                    "std": 0.1,
                    "valid_pixels": 11980,
                },
            ],
            "error": None,
        }

    return app


class UvicornThread(threading.Thread):
    def __init__(self, app: FastAPI, port: int) -> None:
        super().__init__(daemon=True)
        self.config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        self.server = uvicorn.Server(self.config)

    def run(self) -> None:  # pragma: no cover - thread target
        self.server.run()

    def stop(self) -> None:
        self.server.should_exit = True
