# ADR 0002: Satellite data cubes & management-zone delineation

Status: **proposed** · Date: 2026-06-15 · Branch: `claude/satellite-ag-processing-k48asn`

Builds on: `apps/backend/spikes/raster_compute/DECISION.md` (the rasterio+numpy
read path and the synchronous-vs-background-job split) and ADR 0001 (the curated
widget / `render_dashboard` composition layer).

## TL;DR

Add a **multi-temporal data-cube** capability and, on top of it,
**management-zone delineation** — clustering multi-seasonal vegetation patterns
fused with terrain (and, later, soil/yield) into agronomic zones with an
explanation of *why* each zone exists.

The load-bearing decision is a single architectural rule that keeps the agent
thin (CONTEXT.md principle #1):

> **Heavy datasets (cubes, derived layers, zone maps) are content-addressed
> server-side artifacts with stable IDs. The agent manipulates *handles*, never
> pixels. Each cube tool consumes artifact IDs and returns a new artifact ID
> plus a compact summary + a render URL.**

This is the generalization of the two patterns already shipped: the immutable,
hash-keyed `raster_stat_cache`, and the submit→poll→result `raster_jobs` flow.

Chosen path, in tiers:

1. **Enabler (small, ships first):** extend the time-series job to emit a
   **scene manifest** (per-scene IDs + band hrefs), not just scalars. One change
   that unblocks temporal playback (#58) *and* feeds the cube builder.
2. **Cube + temporal features:** `build_cube` and `temporal_features` on
   **in-process xarray + stackstac** behind the existing `geo/` seam, producing
   a **stability ("field memory") COG**. The first per-pixel product; no
   clustering risk yet.
3. **Terrain fusion:** a `geo/terrain.py` DEM provider + terrain derivatives
   (slope/aspect/TWI/curvature), co-registered to the cube grid. Also clears the
   cross-resolution resampling that currently blocks NBR.
4. **Zones + explanation:** a recipe tool `delineate_management_zones` (cluster
   stability + terrain → zone COG + per-zone stats) with HITL save, plus
   `attribute_zones` (driver attribution — the agent's differentiator) and VRA
   prescription export.

Deferred deliberately: TiTiler (we already render COGs client-side via
deck.gl-geotiff — see "Rendering"), a Dask cluster, and soil/yield fusion.

## Context

### Where the imagery pipeline is today

`scene → polygon → scalar`. `geo/raster.py` reads windowed COGs over
`/vsicurl`; `geo/indices.py` computes NDVI/NDWI/EVI as pure numpy functions;
`services/raster_service.py` fans out **one zonal reduction per scene** into a
list of `{datetime, mean, std, …}` points (background job, semaphore-capped,
results cached by `sha256(scene|index|geom|bins)`). Pixels are collapsed at the
earliest possible moment; there is no temporal stack, no per-pixel output, and
no terrain.

Management zones need the opposite shape: **keep pixels, stack them over time,
fuse with terrain, then cluster and explain.** That is a `(x, y, time, band)`
cube plus a small algebra over it — a new primitive, not an extension of the
per-scene path.

### What we can reuse

- **Background-job + immutable-cache patterns** (`raster_jobs`,
  `raster_stat_cache`) — generalize into an artifact registry.
- **Pure index functions** (`indices.py`) — they operate unchanged on xarray
  `DataArray`s, so the band math is portable to the cube path for free.
- **STAC search** (`geo/stac.py`, async) — `search_scenes()` already returns the
  items a cube builder needs.
- **Client-side COG rendering** — the UI already paints COGs with
  `MultiCOGLayer` (`@developmentseed/deck.gl-geotiff`) and inline GLSL colormaps
  (`RasterModule`). A zone map is the same layer with a *discrete* colormap.
- **Snapshot persistence (#20)** — overlays carry their `LayerSource` into the
  thread snapshot and repaint reactively, so a cube/zone artifact becomes a
  durable conversational object with no extra plumbing.
- **Curated widgets + `render_dashboard`** (ADR 0001) — the zone driver report
  needs no new panel type; `StatPanel`/`TablePanel`/`HistogramPanel` cover it.

## The capability ideas (what makes this worth building)

Not "compute NDVI clusters" — that's commodity. The differentiators:

1. **"Field memory" — temporal stability zones.** Reduce the multi-season cube
   per pixel into two axes: **productivity** (multi-year mean/integral NDVI) and
   **stability** (temporal CV). The high-value output is a 3×3 matrix —
   *consistently high / consistently low / unstable* — each cell mapping to a
   distinct decision (invest / investigate the constraint / don't bother with
   variable rate). More actionable than raw k-means, and the product metaphor we
   lead with.
2. **Phenology-shape zones.** Cluster on per-pixel curve metrics (start-of-
   season, peak value/timing, growing-season integral, senescence slope), not
   mean greenness. Distinguishes patches with equal average NDVI but different
   crop development — a genuine edge over typical zone products.
3. **Explainable zones — driver attribution.** After clustering, correlate zone
   membership against each candidate layer (slope, TWI, aspect) via mutual
   information / per-zone distributions; the LLM writes the causal story
   ("low-stable zone coincides with slope >8% + convex curvature → erosion-prone
   → reduced seeding + cover crop"). Numbers from a data tool, synthesis from the
   model. This is where an *agent* beats a GIS tool.
4. **Anomaly-vs-self.** Because the cube holds each pixel's own history, flag
   pixels deviating from *their own* baseline this season (drainage failure,
   pest, machinery skip). Change-vs-self, complementary to change-detection (#25,
   change-vs-time).
5. **Close the loop — VRA export.** Zones → variable-rate prescription map
   (seeding, N) exported as GeoJSON/Shapefile/ISO-XML for the tractor. The
   natural HITL "save/export" endpoint and what makes the feature *matter*.

## Decisions (the open forks, resolved)

These are the architectural choices the cube path forces. Marked recommended;
this ADR is **proposed** pending owner sign-off.

### D1 — Cube as content-addressed artifact  ✅

New backend `artifacts` registry: `(id, type, recipe_hash, status, storage_uris,
summary_json, provenance, created_at)`, reused by `recipe_hash`. Artifact types:
`cube`, `temporal_layer`, `terrain_layer`, `zone_map`. Outputs are written as
COGs so the existing deck.gl render path displays them directly. This generalizes
`raster_stat_cache` (immutability + hashing) and `raster_jobs` (lifecycle).
**Provenance is intrinsic** — the recipe hash *is* the audit trail ("47 scenes,
2021–2024, NDVI, SCL-masked, k=4 by silhouette").

### D2 — Compute engine: in-process xarray + stackstac for v1  ✅

Add `xarray` + `stackstac` (+ `rioxarray` for resampling) behind the `geo/` seam.
**No Dask cluster, no separate worker service yet** — consistent with the
raster-compute spike's "don't stand up infra we don't need." Field/farm-scale
AOIs over a few seasons fit comfortably in memory on a background job. Dask
remains the documented escape hatch behind the same service interface.
`indices.py` stays pure functions (work on `DataArray`s unchanged).

- *Rejected for v1:* a standing Dask/worker cluster (premature; always-on cost).
- *Trigger to revisit:* AOIs beyond single-farm scale, or cube builds that
  exceed the job's memory/time budget.

### D3 — Storage: object storage (MinIO dev / S3 prod)  ✅

Artifact COGs live in object storage; the browser fetches them directly via the
existing deck.gl-geotiff path (mirrors how `sentinel-cogs` is read today). Add
MinIO to the compose stack for local dev.

- *Rejected:* PostGIS out-db raster (couples raster lifecycle to the DB, no
  client-direct read path, fights the established COG-over-HTTP pattern).

### D4 — Rendering: reuse `MultiCOGLayer`; TiTiler deferred  ✅

A management-zone overlay is `MultiCOGLayer` with a **discrete/step colormap**
instead of a continuous one. So per-pixel classified overlays need: a zone COG
(D1/D3) + one new `LayerSource` arm + one categorical colormap. **TiTiler is a
later scale optimization, not a v1 prerequisite.**

### D5 — Tool surface: recipe-first + primitives as escape hatch  ✅

Ship one opinionated high-level tool, `delineate_management_zones`, that runs the
whole pipeline server-side (the 90% path), **and** expose mid-level primitives
(`build_cube`, `temporal_features`, `terrain_derive`, `attribute_zones`) for
exploration and the "re-cluster into 3 / drop the drought year" follow-ups.
Chaining only micro-tools is token-heavy and error-prone for the model; a single
recipe tool keeps trajectories reliable and eval-able.

### D6 — v1 fusion scope: terrain only  ✅

v1 clusters temporal-stability features + terrain derivatives. Soil (SoilGrids),
uploaded yield-monitor data, weather/GDD, and ECa are deferred — but the
clustering input is built as a **generic aligned feature stack** (the
"align layer to cube grid" step), so adding layers later is data, not
architecture.

## What it means for each app

**Backend** — new `artifacts` registry + object storage; generalize the job
framework (async is the default for cube ops, with progress streamed for the
playback/progress widget); `geo/cube.py` (stackstac build + temporal reduction),
`geo/terrain.py` (DEM provider + derivatives), `geo/zones.py` (standardize →
cluster → smooth/sieve → vectorize); cluster-count selection via a validity
index (silhouette/FPI). The cross-resolution resampling solved here also
unblocks **NBR** (20 m SWIR onto the 10 m grid) — solve once, generally.

**Agent** — tools become an **algebra over handles** (consume/return artifact
IDs + summaries); the async "submit → check → render" loop and the new recipe
tool get documented in `prompts/system.py`, extending the load-bearing
"Agriculture workflow sequence". New UI tools (`add_zone_layer`, zone legend)
return acks only; zone stats + attribution come from **data** tools (the
UI-vs-data invariant, applied to a richer surface). HITL `interrupt()` +
`ApprovalWidget` gate "save zone map / export prescription".

**UI** — new `LayerSource` arm
`{ kind: "zones"; href; colormap; classes }`, persisted in the thread snapshot
(#20) so zones survive reopen and stay iterable; one categorical colormap; one
curated `management-zones` widget (legend + per-zone stats table + attribution
narrative — the narrative reuses dashboard panels).

## Consequences

- A new heavyweight dependency tier (`xarray`, `stackstac`, `rioxarray`) and an
  object-store dependency (MinIO in dev). Justified by the cube primitive; scoped
  behind `geo/`.
- The agent gains a genuinely new mode — orchestrating a multi-step server-side
  pipeline — which raises the bar for **evals**: trajectory scoring for the
  recipe path, and **numeric** correctness for zone outputs against synthetic
  fixtures (a planted-gradient field → expected zones). Recordings store
  **handles + summaries only**, never cubes, or replay coverage explodes.
- Zones drive real spend (fertilizer), so provenance (D1) and HITL on
  save/export are non-negotiable, not nice-to-have.
- Agent-side Pydantic schemas and UI-side Zod schemas for the new
  widget/`LayerSource` must be kept in sync (inherent to the split, per ADR
  0001).

## Sequencing

See `docs/roadmap/satellite-data-cubes.md` for the epic / issue breakdown. The
order de-risks each step: manifest enabler → stability product → terrain →
zones+explanation, each shipping value before the next.

## References

- Prior art: `apps/backend/spikes/raster_compute/DECISION.md` (#28); ADR 0001.
- Roadmap: epic #27; related #58 (playback), #25 (change detection), #56
  (imagery intelligence).
- stackstac — <https://stackstac.readthedocs.io/>
- xarray — <https://docs.xarray.dev/>
- deck.gl-geotiff — <https://github.com/developmentseed/deck.gl-geotiff>
