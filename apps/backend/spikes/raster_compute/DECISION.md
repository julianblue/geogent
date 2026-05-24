# Spike: raster-compute architecture (issue #28)

Status: **proposed** · Date: 2026-05-24 · Branch: `claude/spike-raster-compute-bhts2`
Blocks: #22, #23, #24, #26

## TL;DR

Adopt **Option 1 — `rasterio` + `numpy` reading STAC COGs
directly inside FastAPI** for the first quantitative raster features (zonal
stats, single-/few-scene reads). Run reads **synchronously** for single-scene
requests and push **multi-scene time-series onto a background job** from day
one. Do **not** stand up a TiTiler service or a Dask cluster yet — they solve
problems we don't have at current scale and each adds an always-on deployment.
Both remain clean migration targets behind a thin service interface.

The read path is de-risked: the PoC computes zonal mean NDVI for a real
polygon over a live Sentinel-2 scene using windowed COG range reads. See
`poc_zonal_ndvi.py` and "PoC results" below.

## Context

- Backend is **vector-only** today: `geoalchemy2` + `shapely` + PostGIS, no
  `numpy`/`rasterio`/`titiler`/`stackstac`, no server-side COG read path.
- Scenes are already discovered via STAC (Earth Search v1, `sentinel-2-l2a`)
  in two places that we mirror exactly, so the catalog contract is settled:
  - UI: `apps/ui/src/lib/sentinel2.ts` (band hrefs `red`/`green`/`blue`/`nir`/…).
  - Agent: `apps/agent/src/geogent_agent/tools/stac_tools.py`.
- NDVI **visualization** already exists client-side in deck.gl. The new need
  is **quantitative** reads — a number per polygon, and values over time — not
  display.
- The band COGs live in the public `sentinel-cogs` AWS Open Data bucket: plain
  HTTPS range reads, no AWS credentials, proper 1024×1024 internal tiling +
  overviews (verified in the PoC).

## Options evaluated

### Option 1 — `rasterio` + `numpy` in FastAPI  ✅ chosen

Open band COGs over `/vsicurl`, read only the polygon's pixel window, compute
NDVI and zonal stats with numpy in-process. The PoC shows the zonal reduction
is a few lines (`rasterio.features.geometry_mask` + `numpy.nanmean`), so
`rasterstats` is **not** required — see the dependency note below.

- **Pros:** no new service to deploy or monitor; reuses the existing FastAPI
  app, auth, and DB session; lowest moving-parts; windowed reads are fast
  (numbers below); rasterio ships a manylinux wheel with **bundled GDAL** —
  no system GDAL/`apt` packages required.
- **Cons:** CPU/GDAL work runs inside the API process (mitigated: small
  windows, sync only for single-scene, background job for time-series);
  GIL/thread care needed under concurrency; we own caching ourselves.
- **Verdict:** matches the actual first requirement (#22-style single-polygon,
  single-scene zonal stats) with the least infrastructure.

### Option 2 — dedicated **TiTiler** service exposing `/statistics`

A separate FastAPI+rio-tiler container; backend calls its `/cog/statistics`
(and later reuse `/cog/tiles` for server-side tiling).

- **Pros:** battle-tested zonal/statistics endpoint; offloads GDAL CPU off the
  API; same `/tiles` service could later replace client-side rendering.
- **Cons:** a whole extra always-on service to deploy, scale, secure, and pay
  for on Railway; cross-service auth + network hop; today we have **no** tiling
  requirement (deck.gl already renders), so we'd be deploying it only for
  `/statistics` — premature.
- **Verdict:** **deferred.** This is the right escape hatch when (a) GDAL CPU
  starts hurting API latency/availability, or (b) #2x adds server-side tiles.
  Because the backend will call raster compute through one internal module
  (`geo/raster.py`), swapping the in-process call for an HTTP call to TiTiler
  is a localized change.

### Option 3 — `stackstac` + Dask for multi-scene time-series

Build an xarray/dask cube across many scenes and reduce over time.

- **Pros:** the natural tool for large space×time reductions; lazy, chunked,
  parallel.
- **Cons:** heavy dependency stack (xarray, dask, distributed, pyproj,
  rioxarray); a Dask cluster is real ops; overkill for the first
  "NDVI over the season for one field" feature, which is **N independent
  windowed reads** (one per scene) — trivially parallelizable with an async
  task group / process pool and no cluster.
- **Verdict:** **deferred.** Revisit when a feature needs dozens-to-hundreds of
  scenes per request or cross-scene mosaicking. Until then, time-series =
  fan-out of Option-1 windowed reads inside a background job.

## Sync vs. background job

| Request shape | Execution | Why |
|---|---|---|
| 1 polygon × 1 scene (zonal stats) | **synchronous** request | Cold read ≈ 0.7 s/band; well within an HTTP request budget. |
| 1 polygon × N scenes (time-series) | **background job**, poll/stream result | N cold reads × ~0.7 s serially is too long for one request; also shields the API event loop. |

Recommendation: don't add Celery/RQ yet. Start with FastAPI `BackgroundTasks`
(or a small asyncio task + a `raster_jobs` row for status) for time-series, and
graduate to a real queue only if/when concurrency demands it. GDAL work should
run in a thread/process executor so it never blocks the async event loop.

## Caching

Three layers, cheapest first:

1. **GDAL/VSI in-process cache** (free, already on): `VSI_CACHE=TRUE`. In the
   PoC a warm windowed read drops from ~700 ms → **13 ms** within one process.
2. **Result cache** keyed by `(stac_item_id, band_set, polygon_hash, stat)`:
   results are immutable (a scene + polygon never change), so cache
   aggressively in Postgres (or Redis later). This is the highest-value layer
   for repeat agent queries.
3. **HTTP/GDAL block cache to local disk** (`CPL_VSIL_CURL_CACHE` /
   `GDAL_CACHEMAX`) if the same scenes are hit repeatedly across requests —
   optional, add only if measured to help.

## GDAL / container / build impact

Measured in an isolated `uv` venv (Python 3.12) in this container:

- **No system GDAL needed.** The `rasterio` 1.5.0 wheel bundles **GDAL 3.12.1**;
  install is pure `uv pip install`, **~2.5 s**, no `apt` libgdal-dev.
- **Disk footprint** of the added wheels:
  - `rasterio` + `rasterio.libs` (bundled GDAL/PROJ/GEOS): **~112 MB**
  - `numpy` (+libs): **~60 MB**
  - shapely is **already a backend dependency** (no add).
  - Full venv with deps: ~284 MB (includes Python itself).
- **Net image growth ≈ ~150–180 MB** of site-packages on top of the current
  `python:3.12-slim` backend image. No Dockerfile `apt` changes required (the
  existing `build-essential`/`libpq-dev` line is untouched).

### Dependency list to add (to `apps/backend/pyproject.toml`)

```toml
"numpy>=2.1",
"rasterio>=1.4",   # bundles GDAL; manylinux wheel — no system libgdal
```

(Spike pinned the versions it actually ran: `numpy==2.4.6`,
`rasterio==1.5.0`.) `shapely` and `httpx` are already present.

`rasterstats` is intentionally **omitted**: the PoC computes the zonal
reduction directly with `geometry_mask` + numpy, and `rasterstats.zonal_stats`
adds little over that for our windowed single-/few-polygon case while pulling
extra transitive deps. If #22 grows into ergonomic batch multi-polygon ×
multi-stat queries, revisit adding it then. **Not** adding: `titiler`,
`rio-tiler`, `stackstac`, `dask`,
`xarray`, `rioxarray`.

## PoC results (live data)

`poc_zonal_ndvi.py` — zonal mean NDVI, 1 polygon (~1×1 km irrigated field,
Fresno County CA) × 1 Sentinel-2 L2A scene, against the real Earth Search
catalog + `sentinel-cogs` bucket.

```
scene:        S2A_10SGF_20260522_0_L2A  (2026-05-22, cloud 0.0%, EPSG:32610)
window:       93 × 114 px  (9,910 pixels inside polygon)
NDVI mean:    0.406   (min -0.034, max 0.867)  ← plausible for May cropland
```

### Latency / windowed-read notes

| Step | Time |
|---|---|
| STAC search (1 newest low-cloud scene) | ~0.86 s |
| Windowed zonal NDVI, 2 bands, **cold** | ~1.6 s |
| Single-band open + windowed read, **cold** | ~0.7 s |
| Single-band windowed read, **warm** (VSI cache) | **~0.013 s** |
| Naive full-band download (B04) | **229 MB** |
| Naive full-band download (B08) | **228 MB** |

**Windowed vs. full fetch:** the windowed read pulls the COG header (IFD) plus
the handful of internal 1024-px tiles intersecting the polygon — on the order
of **hundreds of KB** — versus **~457 MB** to download both full bands. This is
the entire reason the in-process approach is viable: we are not moving whole
scenes, just the polygon's tiles. Cold latency is dominated by TLS + the first
range request; a result/VSI cache collapses repeats to milliseconds.

## What I could and couldn't run in this container

- ✅ Ran: STAC search, COG open/inspect, windowed reads, NDVI + zonal mean,
  full-band size comparison, dependency install + footprint measurement —
  all against **live** data. Numbers above are real, from this container.
- ⚠️ One workaround, **spike-only**: outbound HTTPS is intercepted by a
  self-signed proxy CA that the wheel-bundled GDAL libcurl wouldn't load via
  `GDAL_HTTP_CAINFO`, so the PoC needs `SPIKE_GDAL_UNSAFE_SSL=1`
  (`GDAL_HTTP_UNSAFESSL=YES`) to read the COGs here. This is a sandbox artifact
  only — in a normal deployment GDAL uses the system trust store against AWS's
  real certs and **no such flag is needed**. The flag is opt-in and off by
  default in the script.

## Out of scope (belongs to #22)

Real endpoints, request/response schemas, auth wiring, the job table/queue,
production caching, and multi-band/multi-stat generalization. This spike only
decides the approach and proves the read path.

## How to run the PoC

```bash
uv venv --python 3.12 /tmp/spike-venv
uv pip install --python /tmp/spike-venv/bin/python rasterio numpy shapely httpx
# In this sandbox only, allow the intercepting proxy's cert:
SPIKE_GDAL_UNSAFE_SSL=1 /tmp/spike-venv/bin/python \
  apps/backend/spikes/raster_compute/poc_zonal_ndvi.py
```
