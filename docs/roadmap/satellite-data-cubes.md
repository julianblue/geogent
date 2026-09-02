# Epic: Satellite data cubes & management-zone delineation

> Roadmap issue body. Paste into a new GitHub issue (child of epic #27) or use
> as-is. Design rationale and the resolved architectural forks live in
> [`docs/adr/0002-satellite-data-cubes-management-zones.md`](../adr/0002-satellite-data-cubes-management-zones.md).

## Goal

Give the agent multi-temporal **data-cube** capabilities and, on top of them,
**management-zone delineation**: cluster multi-seasonal vegetation patterns fused
with terrain into agronomic zones, and explain _why_ each zone exists. Close the
loop with variable-rate prescription export.

## Architecture rule (load-bearing)

Heavy datasets (cubes, derived layers, zone maps) are **content-addressed
server-side artifacts with stable IDs**. The agent manipulates handles, never
pixels; each cube tool consumes artifact IDs and returns a new artifact ID + a
compact summary + a render URL. Generalizes the existing `raster_stat_cache`
(immutable, hashed) and `raster_jobs` (submit→poll→result) patterns.

## Resolved decisions (ADR 0002)

- **Compute:** in-process `numpy` + `rasterio` (`WarpedVRT`) behind the `geo/` seam; no Dask
  cluster, no worker service for v1.
- **Storage:** local-filesystem `ArtifactStore` for v1 (assets served through an
  auth-gated route + same-origin UI proxy); object storage (MinIO/S3) deferred
  behind the same interface.
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

- [x] Build cube in-process on `numpy` + `rasterio` (`WarpedVRT`) — zero new
      deps (ADR 0002 D2 correction; `xarray`/`stackstac` deferred to when we
      persist/serve full cubes). MinIO deferred too — v1 uses a local
      `ArtifactStore`.
- [x] `artifacts` registry (model + migration `0004` + repository + service):
      id, kind, recipe_hash, status, owner, recipe, summary, assets.
- [x] `ArtifactStore` (local-filesystem impl) + asset-serving route; S3/MinIO
      deferred behind the same interface.
- [x] `geo/cube.py` — build a `(time, y, x)` cube from STAC scenes;
      `indices.py` applied over the time dim.
- [x] **Reproject every scene onto one canonical grid** (`WarpedVRT` per band).
      **Load-bearing, not M2:** the spike dropped 20/40 scenes — half the season
      — on grid mismatch when this step was absent. See
      `apps/backend/spikes/cube_zones/DECISION.md`.
- [x] **Per-pixel cloud masking** — `geo/masking.py`: S2 SCL classes
      (0/1/3/8/9/10/11) and Landsat QA_PIXEL bits, warped onto the read grid with
      nearest resampling and applied in BOTH read paths (`raster.zonal_stats` and
      `cube.build_reduction`) before any statistic. Cache/recipe versions bumped
      so pre-mask results are not served.
- [x] `temporal_features` recipe → per-pixel productivity (mean) + stability
      (temporal CV) → **two single-band field-memory GeoTIFF assets**
      (`productivity.tif`, `stability.tif`), via
      `POST /api/v1/analytics/temporal-features`.
- [x] Agent tools: `field_memory_for_field` (submit + poll, returns summary) and
      `show_field_memory` (render a band).
- [x] UI: `fieldMemory` `LayerSource` + `FieldMemoryOverlay` (MultiCOGLayer +
      colormap), persisted/restored in the thread snapshot (#20).
- **Ships:** the first per-pixel product ("field memory"), no clustering risk.
- **De-risked by** `apps/backend/spikes/cube_zones/` (cube builds in-process at
  0.85 MB/field; real within-field structure to cluster).

### M1.5 — Generalize the engine (ag feature → temporal-raster engine)

Turns the field-memory pipeline into a general temporal-raster engine without
re-architecting; each piece reuses the cube/artifact/render scaffold.

- [x] **Pluggable reducer registry** (`geo/reducers.py`): `field_memory`,
      `composite` (median), `trend` (per-pixel slope/yr), `frequency` (fraction
      above a threshold). Recipe gains `reducer` + `reducer_params`; each output
      declares a `colormap` id the UI resolves (rdylgn/stability/diverging/
      sequential).
- [x] **Extended indices + SWIR unblock**: NBR (implemented), NDMI, MNDWI,
      NDRE, SAVI; `zonal_stats` warps bands with `WarpedVRT` so SWIR/red-edge
      co-register everywhere (not just the cube path).
- [x] **Arbitrary AOI**: `field_id` | `geometry_wkt` | `bbox`; hard pixel-cap
      guard (`cube_max_pixels`, default 4M @ 10 m) → 422 (decision: reject, not
      auto-coarsen).
- [x] **Collection registry** (`geo/collections.py`): Sentinel-2 L2A + Landsat
      C2 L2 via logical-band aliasing; per-sensor DN→reflectance scale/offset so
      the index kernels are sensor-agnostic (EVI/SAVI de-hardcoded off the S2
      `/10000`); per-collection index availability validated (e.g. NDRE rejected
      on Landsat, which has no red-edge band).
- [ ] **Follow-ups:** SAR (Sentinel-1 RTC — own backscatter index family);
      reducer-output colormap value-range tuning once seen on real data;
      phenology-shape reducer (argmax/integral) as an alternate clustering input.

### M2 — Terrain fusion

- [ ] `geo/terrain.py` — DEM provider (Copernicus GLO-30 via STAC) + derivatives
      (slope/aspect/TWI/curvature), co-registered to the cube grid (**reuses the
      M1 reprojection primitive**).
- [ ] The same align-to-grid step also **unblocks NBR** (20 m SWIR → 10 m).
- [ ] Agent primitive `terrain_derive`.

### M3 — Management zones + explanation

- [x] `geo/zones.py` — standardize → k-means (k-means++ seeding, fixed seed for
      reproducible maps) with Calinski-Harabasz cluster-count selection →
      majority filter + `rasterio.features.sieve` → vectorize to WGS84. Zones
      are relabelled by ascending primary-feature mean, so "zone 1" is the
      weakest ground on every field.
- [x] `management_zones` artifact kind + `POST /api/v1/analytics/management-zones`
      → `zones.tif` (discrete colormap) **and** `zones.geojson` (the exportable
      boundaries M4's VRA path builds on). One scene search, one grid, one cube
      per index, so multi-index feature stacks are co-registered by construction.
- [x] Driver attribution in-line (per-feature eta²: the share of variance that
      lies between zones) rather than as a separate `attribute_zones` call — the
      "why" ships with the map, and the agent writes the narrative from it.
- [x] Agent tool `delineate_management_zones(field/aoi, indices, n_zones="auto")`.
- [ ] HITL save via `interrupt()` + `ApprovalWidget` — deferred with M4's export;
      there is nothing to persist until a prescription exists.
- [x] UI: discrete `zones` colormap in the shared registry; the existing
      artifact-raster overlay renders it, so no new layer kind was needed.
- [ ] Curated `management-zones` widget (legend + stats table + narrative) —
      today the agent presents zone stats through `render_dashboard`.

### M4 — Close the loop

- [ ] VRA prescription export (GeoJSON/Shapefile/ISO-XML) behind HITL.
- [ ] Anomaly-vs-self detection (pixel deviates from its own baseline).
- [ ] (Stretch) phenology-shape features as an alternate clustering input.

## Evals

- [ ] Trajectory scoring for the recipe path (multi-step pipeline).
- [x] Numeric correctness for zone outputs vs synthetic planted fields
      (`tests/geo/test_zones.py`: two-patch recovery, auto-k on a three-level
      field, attribution, determinism, speckle removal, area accounting).
- [ ] Recordings store handles + summaries only — never cubes.

## Out of scope (tracked, not built here)

TiTiler service; Dask cluster; soil (SoilGrids) / yield-monitor / weather fusion;
user-defined custom band-math indices.
