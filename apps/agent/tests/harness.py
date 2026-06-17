"""Shared test harness helpers for the live-LLM suites (e2e + evals).

Both suites need the same plumbing: a free port, a readiness poll, a FastAPI
stub mimicking the geogent backend, and a thread that serves it. These live
here as plain importable functions so ``tests/conftest.py`` can expose them as
fixtures and ``tests/e2e/conftest.py`` can reuse the reachability probe without
duplicating code.

``backend_stub_server`` and ``langgraph_dev_server`` are pytest-free context
managers so non-pytest entry points (``tests/evals/experiment.py``) can boot
the same stack; the conftest fixtures are thin wrappers around them.
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
import uvicorn
from fastapi import FastAPI

# tests/harness.py -> tests/ -> apps/agent
AGENT_DIR = Path(__file__).resolve().parents[1]

# Model the live suites (and experiments) drive when none is pinned explicitly.
DEFAULT_TEST_MODEL = "openrouter:google/gemini-2.5-flash"


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

    # Canned EuroCrops-style parcels (Brandenburg/Uckermark flavor) so the
    # crop-query tools have deterministic data; crop names use the real HCAT
    # vocabulary the ingest script imports.
    parcels_fixture = [
        {
            "id": 201,
            "name": "DE-BB DEBBNF0000201",
            "crop": "winter_common_soft_wheat",
            "season": "2023",
        },
        {
            "id": 202,
            "name": "DE-BB DEBBNF0000202",
            "crop": "winter_common_soft_wheat",
            "season": "2023",
        },
        {
            "id": 203,
            "name": "DE-BB DEBBNF0000203",
            "crop": "winter_rapeseed_rape",
            "season": "2023",
        },
        {"id": 204, "name": "DE-BB DEBBNF0000204", "crop": "winter_barley", "season": "2023"},
        {
            "id": 205,
            "name": "DE-BB DEBBNF0000205",
            "crop": "pasture_meadow_grassland_grass",
            "season": "2023",
        },
        {"id": 206, "name": "DE-BB DEBBNF0000206", "crop": "green_silo_maize", "season": "2023"},
        {"id": 207, "name": "DE-BB DEBBNF0000207", "crop": "sugar_beet", "season": "2023"},
    ]

    @app.get("/api/v1/fields")
    def list_fields() -> list[dict]:
        return [
            {"id": 7, "name": "North Forty", "crop": "corn", "season": "2026"},
            *parcels_fixture,
        ]

    @app.get("/api/v1/fields/in-bbox")
    def fields_in_bbox(
        min_lon: float,
        min_lat: float,
        max_lon: float,
        max_lat: float,
        crop: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        rows = [p for p in parcels_fixture if crop is None or crop.lower() in p["crop"]]
        return rows[: limit or len(rows)]

    @app.get("/api/v1/fields/crop-stats")
    def crop_stats(min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> list[dict]:
        # Ordered by area, dominant crop first — same contract as the backend.
        return [
            {"crop": "winter_common_soft_wheat", "parcels": 81, "total_area_ha": 1843.5},
            {"crop": "pasture_meadow_grassland_grass", "parcels": 147, "total_area_ha": 1210.4},
            {"crop": "winter_rapeseed_rape", "parcels": 40, "total_area_ha": 612.3},
            {"crop": "winter_barley", "parcels": 48, "total_area_ha": 588.1},
            {"crop": "green_silo_maize", "parcels": 10, "total_area_ha": 142.7},
            {"crop": "sugar_beet", "parcels": 11, "total_area_ha": 95.2},
        ]

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

    # --- routing / geocoding (#55): mirror apps/backend response shapes -------

    @app.post("/api/v1/routing/route")
    def route(payload: dict) -> dict:
        coords = payload.get("coordinates") or [[0.0, 0.0], [0.0, 0.0]]
        first = coords[0]
        last = coords[-1]

        def _pt(c: object) -> list[float]:
            if isinstance(c, dict):
                return [c.get("longitude", 0.0), c.get("latitude", 0.0)]
            return list(c)  # type: ignore[arg-type]

        return {
            "distance_m": 21340.0,
            "duration_s": 1530.0,
            "profile": payload.get("profile", "driving"),
            "geometry": {"type": "LineString", "coordinates": [_pt(first), _pt(last)]},
        }

    @app.post("/api/v1/routing/matrix")
    def matrix(payload: dict) -> dict:
        n = max(len(payload.get("coordinates") or []), 1)
        durations = [[0.0 if i == j else 1200.0 for j in range(n)] for i in range(n)]
        distances = [[0.0 if i == j else 25000.0 for j in range(n)] for i in range(n)]
        return {
            "durations_s": durations,
            "distances_m": distances,
            "profile": payload.get("profile", "driving"),
        }

    @app.post("/api/v1/routing/isochrone")
    def isochrone(payload: dict) -> dict:
        lon = payload.get("longitude", 0.0)
        lat = payload.get("latitude", 0.0)
        d = 0.05
        ring = [
            [lon - d, lat - d],
            [lon + d, lat - d],
            [lon + d, lat + d],
            [lon - d, lat + d],
            [lon - d, lat - d],
        ]
        return {
            "profile": payload.get("profile", "driving"),
            "range_minutes": payload.get("range_minutes", [10]),
            "geojson": {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {},
                        "geometry": {"type": "Polygon", "coordinates": [ring]},
                    }
                ],
            },
        }

    @app.get("/api/v1/geocode")
    def geocode(q: str, limit: int = 5) -> dict:
        return {
            "results": [
                {
                    "display_name": f"{q}, France",
                    "longitude": 2.3522,
                    "latitude": 48.8566,
                    "type": "city",
                    "bbox": [2.2, 48.8, 2.5, 48.9],
                }
            ]
        }

    @app.get("/api/v1/geocode/reverse")
    def reverse_geocode(lon: float, lat: float) -> dict:
        return {
            "display_name": "Champ de Mars, 5 Avenue Anatole France, Paris, France",
            "longitude": lon,
            "latitude": lat,
            "type": "tourism",
            "address": {"city": "Paris", "country": "France"},
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


@contextlib.contextmanager
def backend_stub_server() -> Iterator[str]:
    """Serve the backend stub on a free port; yields its base URL."""
    port = free_port()
    thread = UvicornThread(build_backend_stub(), port)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    wait_for(f"{base}/openapi.json", timeout=15.0)
    try:
        yield base
    finally:
        thread.stop()
        thread.join(timeout=5.0)


@contextlib.contextmanager
def langgraph_dev_server(
    backend_url: str,
    *,
    model: str | None = None,
    n_jobs_per_worker: int = 1,
    log_name: str = ".langgraph_dev.log",
) -> Iterator[str]:
    """Spawn ``langgraph dev`` against the local agent directory; yields its URL.

    ``n_jobs_per_worker`` matters for experiments: the dev server queues runs
    behind a single worker job by default, so concurrent eval runs serialize
    (and can hit the SDK's read timeout) unless it is raised to match the
    client-side concurrency. ``model`` pins AGENT_MODEL for the subprocess;
    when omitted, TEST_AGENT_MODEL / the suite default applies.
    """
    port = free_port()
    env = os.environ.copy()
    env["BACKEND_URL"] = backend_url
    if model is not None:
        env["AGENT_MODEL"] = model
    else:
        env.setdefault("AGENT_MODEL", os.getenv("TEST_AGENT_MODEL", DEFAULT_TEST_MODEL))
    # Disable LangSmith hooks so the agent under test doesn't try to call out.
    env.setdefault("LANGSMITH_TRACING", "false")
    env.pop("LANGCHAIN_TRACING_V2", None)

    log_path = AGENT_DIR / log_name
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
            "--no-reload",
            "--n-jobs-per-worker",
            str(n_jobs_per_worker),
        ],
        cwd=AGENT_DIR,
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        wait_for(f"{base}/ok", timeout=90.0)
        yield base
    finally:
        proc.terminate()
        with contextlib.suppress(Exception):
            proc.wait(timeout=10)
        if proc.poll() is None:
            proc.kill()
        log_file.close()
