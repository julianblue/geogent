# Epic: Satellite data cubes & management-zone delineation

> Roadmap issue body. Paste into a new GitHub issue (child of epic #27) or use
> as-is. Design rationale and the resolved architectural forks live in
> [`docs/adr/0002-satellite-data-cubes-management-zones.md`](../adr/0002-satellite-data-cubes-management-zones.md).

## Goal

Give the agent multi-temporal **data-cube** capabilities and, on top of them,
**management-zone delineation**: cluster multi-seasonal vegetation patterns fused
with terrain into agronomic zones, and explain *why* each zone exists. Close the
loop with variable-rate prescription export.

## Architecture rule (load-bearing)

Heavy datasets (cubes, derived layers, zone maps) are **content-addressed
server-side artifacts with stable IDs**. The agent manipulates handles, never
pixels; each cube tool consumes artifact IDs and returns a new artifact ID + a
compact summary + a render URL. Generalizes the existing `raster_stat_cache`
(immutable, hashed) and `raster_jobs` (submit→poll→result) patterns.

## Resolved decisions (ADR 0002)

- **Compute:** in-process `xarray` + `stackstac` behind the `geo/` seam; no Dask
  cluster, no worker service for v1.
- **Storage:** object storage (MinIO dev / S3 prod), COGs fetched client-side.
- **Rendering:** reuse `MultiCOGLayer` with a discrete colormap; **TiTiler
  deferred**.
- **Tool surface:** recipe-first (`delineate_management_zones`) + mid-level
  primitives as an escape hatch.
- **v1 fusion scope:** terrain only; soil/yield deferred but the clustering input
  is a generic aligned feature stack.

## Milestones

### M0 — Scene-manifest enabler (small; unblocks #58 too)
- [ ] Extend the time-series result (or add a parallel manifest output) to carry
      per-scene IDs + band hrefs, not just scalars.
- [ ] Wire the manifest into the temporal-playback scrubber (#58).
- **Why first:** tiny change, ships playback value immediately, and is the input
  manifest the cube builder needs.

### M1 — Data cube + "field memory"
- [ ] Add `xarray`/`stackstac`/`rioxarray` deps + MinIO to the compose stack.
- [ ] `artifacts` registry (table + service): id, type, recipe_hash, status,
      storage_uris, summary, provenance.
- [ ] `geo/cube.py` — build a `(x, y, time, band)` cube from a STAC manifest;
      `indices.py` applied over the time dim.
- [ ] **Reproject every scene onto one canonical grid** (stackstac
      `epsg=/resolution=/bounds=`, or `WarpedVRT`). **Load-bearing, not M2:** the
      spike dropped 20/40 scenes — half the season — on grid mismatch when this
      step was absent. See `apps/backend/spikes/cube_zones/DECISION.md`.
- [ ] **Per-pixel SCL cloud masking** (drop classes 3/8/9/10/11), resampled to
      the 10 m grid — without it, residual cloud/shadow inflates temporal CV and
      fakes "instability".
- [ ] `temporal_features` — per-pixel productivity (mean/integral) + stability
      (CV) → **stability COG** artifact.
- [ ] Agent primitives `build_cube`, `temporal_features` (handles in/out).
- [ ] UI: `LayerSource` arm for a single-band index COG + continuous colormap;
      persisted in the thread snapshot (#20).
- **Ships:** the first per-pixel product ("field memory"), no clustering risk.
- **De-risked by** `apps/backend/spikes/cube_zones/` (cube builds in-process at
      0.85 MB/field; real within-field structure to cluster).

### M2 — Terrain fusion
- [ ] `geo/terrain.py` — DEM provider (Copernicus GLO-30 via STAC) + derivatives
      (slope/aspect/TWI/curvature), co-registered to the cube grid (**reuses the
      M1 reprojection primitive**).
- [ ] The same align-to-grid step also **unblocks NBR** (20 m SWIR → 10 m).
- [ ] Agent primitive `terrain_derive`.

### M3 — Management zones + explanation
- [ ] `geo/zones.py` — standardize features → cluster (k-means / fuzzy c-means)
      with validity-index cluster-count selection → smooth/sieve → vectorize.
- [ ] Recipe tool `delineate_management_zones(field/aoi, years, indices,
      extra_layers, n_zones="auto", mask)` → zone COG + per-zone stats.
- [ ] `attribute_zones` — driver attribution (mutual information / per-zone
      distributions); LLM writes the causal narrative.
- [ ] HITL save via `interrupt()` + `ApprovalWidget`.
- [ ] UI: discrete colormap + `{ kind: "zones" }` `LayerSource` + curated
      `management-zones` widget (legend + stats table + attribution narrative).

### M4 — Close the loop
- [ ] VRA prescription export (GeoJSON/Shapefile/ISO-XML) behind HITL.
- [ ] Anomaly-vs-self detection (pixel deviates from its own baseline).
- [ ] (Stretch) phenology-shape features as an alternate clustering input.

## Evals
- [ ] Trajectory scoring for the recipe path (multi-step pipeline).
- [ ] Numeric correctness for zone outputs vs a synthetic planted-gradient field.
- [ ] Recordings store handles + summaries only — never cubes.

## Out of scope (tracked, not built here)
TiTiler service; Dask cluster; soil (SoilGrids) / yield-monitor / weather fusion;
user-defined custom band-math indices.
