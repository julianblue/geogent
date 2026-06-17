# Spike: data-cube + "field memory" read path (issue #65 / ADR 0002 M1)

Status: **proposed** · Date: 2026-06-15 · Branch: `claude/satellite-ag-processing-k48asn`
Builds on: `../raster_compute/DECISION.md` (#28) · ADR 0002

## TL;DR

The M1 cube path is **de-risked and viable in-process.** The PoC
(`poc_field_memory_cube.py`) builds a real multi-date NDVI cube for one field
over a season, reduces it **per pixel over time** into the two "field memory"
layers ADR 0002 leads with — productivity (mean NDVI) and stability (temporal
CV) — and writes them as a renderable GeoTIFF. Against live Earth Search /
`sentinel-cogs` data this confirms:

- **In-process xarray/numpy is the right v1 compute (ADR 0002 D2).** The whole
  field cube is **0.85 MB** in memory (20 dates × 114 × 93 px). No Dask, no
  worker service — a background job is plenty.
- **There is real within-field structure to cluster (the feature is worth
  building).** Across the polygon, productivity spread std **0.174** and
  stability spread std **0.108** — pixels genuinely differ in how productive
  *and* how stable they are. A flat field would show near-zero spread; this
  doesn't.
- **The output is a standard COG the existing renderer can paint (D1/D4).** A
  2-band tiled GeoTIFF (`productivity_mean_ndvi`, `stability_temporal_cv`),
  73 KB, no TiTiler involved.

**One finding changes the plan:** cross-tile/cross-orbit **reprojection must
move into M1, not wait for M2.** Half the season's scenes land on a different
pixel grid and are currently dropped — see below.

## What the PoC proves

`poc_field_memory_cube.py` — same ~1.5 km Fresno County field as the
`raster_compute` spike, season 2025-03-01..2025-10-31, cloud < 20%.

```
STAC search (40 scenes in season)                 ~1.0 s
build cube: 20 cold windowed reads, stacked        ~22  s   (~1.1 s/scene)
  cube shape (t,y,x): (20, 114, 93)  =  0.85 MB in memory
  stacked 20 scenes, SKIPPED 20 (grid mismatch)
  dates actually covered: 2025-03-01 .. 2025-07-14
per-pixel temporal reduction (mean + CV)            3  ms
write 2-band tiled GeoTIFF                          ~15 ms   (72.8 KB)

productivity (mean NDVI): mean 0.393, range [-0.027, 0.835]
stability  (temporal CV): mean 0.200, range [ 0.038, 1.787]
valid obs/pixel: 20 (all stacked dates), 9,911 px in polygon
```

The per-pixel temporal stack is trivial once the grids align
(`np.stack` → `np.nanmean`/`np.nanstd` over axis 0). The cost and the risk are
entirely in *getting every scene onto one grid* and in *what counts as a valid
observation* (cloud masking) — not in the reduction.

## Decisions confirmed (ADR 0002)

| Decision | Verdict from the spike |
|---|---|
| **D2** in-process xarray/stackstac, no Dask for v1 | ✅ Cube is sub-MB at field scale; reduction is milliseconds. Dask would be pure overhead here. |
| **D1/D3** artifact = COG | ✅ Result writes as a 73 KB tiled GeoTIFF; production swaps `driver="GTiff"` → `driver="COG"` + object storage. |
| **D4** reuse `MultiCOGLayer`, defer TiTiler | ✅ Output is a plain COG; nothing here needs a tile server. |
| **D5** recipe + primitives | ✅ The script *is* the `build_cube` → `temporal_features` primitive chain; wrapping it as one recipe is straightforward. |

## Finding that changes the plan: pull reprojection into M1

The PoC stacks only scenes whose `(crs, transform)` exactly matches the first
scene's grid; **20 of 40 scenes were skipped** because a small field falls under
multiple MGRS tiles / relative orbits with different UTM origins (and sometimes
different EPSG). The consequence is not just fewer scenes — it **truncated the
time span** to 2025-03-01..2025-07-14 (the dominant tile's passes), silently
dropping the back half of the season.

That is exactly the "align layer to cube grid" step ADR 0002 scheduled for
**M2 (terrain fusion)**. The spike shows it is **load-bearing for M1 itself**:
without it, the cube is "works on a demo field that happens to sit in one tile",
not "works on any field". Recommendation:

- **Move the canonical-grid resampling step (rioxarray / `WarpedVRT` reproject
  onto a fixed target grid) into M1**, before shipping the stability product.
  stackstac does this natively (`epsg=`, `resolution=`, `bounds=`), which is an
  additional point in favour of adopting it for the cube builder rather than
  hand-rolling windowed reads as the PoC does.
- Terrain co-registration (M2) then reuses the *same* resampling primitive — so
  this is a re-ordering, not new scope.

## Second gap: per-pixel cloud masking (SCL)

The PoC, like today's pipeline, filters clouds only at **scene level**
(`eo:cloud_cover < 20`). For a *per-pixel* temporal product that is not enough:
a single cloudy or shadowed pixel left in a pixel's time series inflates its
temporal CV and biases its mean, manufacturing fake "instability". M1 needs
**per-pixel SCL masking** (drop classes 3/8/9/10/11), which means reading the
20 m SCL band and resampling it onto the 10 m grid — the *same* resampling
primitive again. Defer-but-track for the stability product to be trustworthy.

## Dependency / footprint impact

No new system packages. The cube path adds, on top of the `numpy`+`rasterio`
already proposed in #28:

```toml
"xarray>=2024.0",
"stackstac>=0.5",
"rioxarray>=0.15",   # WarpedVRT-style reprojection onto the cube grid
```

The PoC itself ran on **only** `rasterio numpy shapely httpx` (no xarray/
stackstac) — deliberately, to prove the read/stack/reduce path is not
dependent on them; they are the production *ergonomics* (lazy chunked cubes,
built-in reprojection), not a correctness requirement.

## Out of scope (belongs to M1/M3 proper)

Artifact registry + object storage, the recipe/primitive tools, zone clustering
(M3), the `COG` driver + overviews, and production cloud masking. This spike
decides the approach and proves the cube/stack/reduce/write path on live data.

## How to run the PoC

```bash
uv venv --python 3.12 /tmp/spike-venv
uv pip install --python /tmp/spike-venv/bin/python rasterio numpy shapely httpx
# Sandbox only — allow the intercepting proxy's cert (see raster_compute spike):
SPIKE_GDAL_UNSAFE_SSL=1 /tmp/spike-venv/bin/python \
    apps/backend/spikes/cube_zones/poc_field_memory_cube.py
```

Writes `/tmp/field_memory.tif` (2-band: productivity, stability). In a normal
deployment GDAL uses the system trust store and no `SPIKE_GDAL_UNSAFE_SSL` flag
is needed.
