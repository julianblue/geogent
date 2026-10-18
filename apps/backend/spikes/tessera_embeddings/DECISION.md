# Spike: TESSERA embeddings read path + field sources (ADR 0003 / P0)

Status: **proposed** · Date: 2026-10-18 · Branch: `feat/tessera-embeddings-spike`
ADR: `docs/adr/0003-tessera-embeddings-and-deep-analysis.md`
Builds on: `../raster_compute/DECISION.md` (#28) · `../cube_zones/DECISION.md` (#65)

## TL;DR

Both halves of the P0 read path are **de-risked and cheap enough to run in the
backend**, with four findings that change the plan:

- **TESSERA reads work** with direct `icechunk` + `xarray`, anonymously, with no
  proxy/TLS workaround. A field-scale AOI (10.4 km², 4 chunks/array/year) costs
  **~1.2–1.7 s and ~34 MB per year** cold; the rule of thumb is **~8 MB per
  6.5 km² chunk-year**. The icechunk default has **no chunk cache** — repeat
  reads re-download — so production needs its own.
- **Declared parcels are cheap and rich; FTW predicted polygons are coarse.**
  Austrian declared data (harmonized, CC-BY-4.0) comes back in ~4.5 s / 3.4 MB
  for 371 fields with real crop codes. FTW polygons have a median of 6 ha and
  contain ~2 declared parcels each: **usable as field extents, not as
  crop-label units.** Crop/regime inference must be per-pixel or per
  sub-polygon cluster inside FTW polygons.
- **"Year" is the calendar year** (confirmed from store metadata). Winter crops
  straddle two annual embeddings.
- **The license is unresolved and cannot be settled from the data side:** no
  license anywhere in the store, mirror, registry, or API. Keep derived
  products private per user until Cambridge/dClimate answer.

- **Field-level embeddings carry strong crop/season signal** (join
  experiment, ~350 parcels, one AOI): a standardised logistic regression on
  field means reaches **~0.85 season-regime and ~0.81 crop (HCAT) accuracy**
  vs ~0.29 / 0.23 majority; year-centred embedding distance flags crop
  rotation at **AUC 0.90**; per-pixel clustering splits merged FTW blocks into
  declared parcels at **median ARI 0.82** (spatial baseline 0.13). Rare classes
  (grassland, spring crops) and within-regime crop swaps are the weak spots.

## Context

- ADR 0003 adds pixel-embedding analytics on top of TESSERA v1.1 (annual,
  128-d int8, 10 m, 2017-2025) and needs, per field, an embedding **and** a
  field boundary (+ ideally a crop label to train on).
- The store is `s3://tessera-embeddings/v1.1/dclimate.icechunk` (Icechunk /
  Zarr v3, us-west-2, ~66 TiB). It can only ever be read in windows.
- Field boundaries and labels come from Fields of the World (FTW) on Source
  Cooperative: harmonized **declared** national data and global **predicted**
  boundaries. Which of these can serve as the "unit of analysis" was open.
- Neither spike touches FastAPI, auth, the DB, or the artifact registry. Both
  scripts run in an isolated venv; no backend dependency is added.

## What each PoC proves

### `poc_tessera_read.py` — TESSERA read path

For a Marchfeld AOI (lon 16.58-16.62, lat 48.24-48.27 = 340 x 305 px, 10.4 km²)
over 2021-2025 it: opens the repo anonymously, slices UTM group `33N`,
dequantises (`int8 x scales`), reads the QC arrays, measures cold/repeat
latency and bytes, and derives per-pixel year-over-year cosine distance and a
PCA(3) false-colour GeoTIFF. It exposes a reusable
`read_embeddings(bbox_wgs84, years)` for the join step.

### `poc_field_sources.py` — declared vs. predicted field boundaries

For the same AOI it pulls declared parcels (harmonized INVEKOS, 2024 + 2025)
and FTW predicted polygons by HTTP range read only, normalises both to one
schema in EPSG:4326, reports crop-class / field-size distributions, IoU-matches
FTW against declared, and derives a draft HCAT -> season-regime mapping
(`SEASON_REGIME_BY_HCAT`, longest-prefix).

## PoC results

### TESSERA store (confirmed schema)

| Property          | Value                                                                                                                                                |
| ----------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| Stack that worked | icechunk 2.3.0, zarr 3.4.1, xarray 2026.9.0, numcodecs 0.17.0 + pcodec 1.0.4, rasterio 1.5.2, pyproj 3.8.0, Python 3.12                              |
| Group `33N` dims  | time=9 (2017-2025), northing=933888, easting=67584, band=128, month=12                                                                               |
| Chunking          | 256 x 256 x 128 x 1 yr, in 2048² shards, zstd; **~8.1 MB per chunk-year** (embeddings + scales)                                                      |
| Grid              | 10 m north-up, `spatial:transform` `[10,0,163840,0,-10,9338880]`, corner origin, coords are pixel centres, northing descending, origin chunk-aligned |
| Root attrs        | `geoemb:*` — model `geotessera.org/model/1.1`, `optical_min_obs=15`, per-pixel-scale int8                                                            |
| Group attrs       | `years_complete`, `runs` (per-year provenance)                                                                                                       |
| Repo              | branch `main` + `zone-XXN-YEAR` tags; latest snapshot 2026-09-14                                                                                     |
| Year convention   | `time_convention="calendar_year"`, `time_bnds` Jan 1 -> Jan 1, S2 input 01-01..12-31                                                                 |

Unfilled preallocated years read as fill values — **check `years_complete`**
before trusting a year. 2017 is thinner (Sentinel-2B ramp-up).

### TESSERA read latency and bytes

Measured from this container via the agent proxy — **not** us-west-2, so
absolute numbers are pessimistic for a co-located backend.

| Step                                   | Time / size                                               |
| -------------------------------------- | --------------------------------------------------------- |
| Repo open                              | ~0.8 s                                                    |
| Group open                             | ~1.6-1.9 s                                                |
| Embeddings + scales, 1 year, cold      | 1.2-1.7 s (~34 MB, 4 chunks)                              |
| Per chunk, cold                        | ~0.3-0.4 s (a single 8 MB chunk ~0.8 s)                   |
| Same year, repeat                      | ~0.9 s (**no cache; re-downloads**)                       |
| 5 years threaded, cold                 | 2.4 s (~170 MB)                                           |
| 5 years threaded, repeat               | 1.2 s                                                     |
| QC arrays (obs counts, month coverage) | only ~0.7 MB/yr but 1.4-2 s latency (many small requests) |

QC arrays are cheap in bytes but expensive in round-trips: **read them on
demand, not by default.**

### TESSERA data quality (Marchfeld AOI, cropland)

| Check                         | Result                                                                                                            |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| NaN / +inf scales             | 0%                                                                                                                |
| Scale range                   | 0.008-0.095                                                                                                       |
| Dequantised value range       | -12..+9                                                                                                           |
| `s2_obs_count` / year         | 45-85 (2025 median 75 vs 59-66 other years)                                                                       |
| S1 asc/desc obs               | 56-115 every year — the store docs claim zero S1 for a 33N tile in 2022-24, so **S1 coverage varies by location** |
| Months covered                | all 12                                                                                                            |
| YoY per-pixel cosine distance | median ~0.26; mean 0.24-0.26 every pair; min ~0.003; p99 0.42-0.45                                                |
| PCA(3), 2024                  | variance ratios 0.23 / 0.15 / 0.09                                                                                |

Use `scales` NaN as the coverage mask. The large, uniform YoY distance is
consistent with crop rotation on cropland (the join experiment tests this).

### UTM zone seams

The `33N` array is wider than the nominal 6° band (it has data at 11.9°E and
18.1°E); neighbouring zones overlap by **at most one tile**, so reading from
the **nominal** zone is safe. The spike provider raises `NotImplementedError`
for a bbox that crosses a zone boundary. Austria's 12°E boundary cuts
Tyrol/Salzburg, so this is not a corner case for the target region.

### Field sources — endpoints

| Source                | Location                                                                                                                         | Notes                                                                                                                                                                                                                                                           |
| --------------------- | -------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Declared (harmonized) | `https://data.source.coop/ftw/harmonized-field-data/at/year=<Y>/at-<Y>.parquet`, Y = 2015-2025 (`at/latest/at.parquet` = 2025)   | 2.94M fields, 851 MB (latest). CC-BY-4.0 (Agrarmarkt Austria; EuroCrops V2 for 2015-2017). License is in `collection.json` + file metadata, mostly **absent from per-year item JSON**. CRS EPSG:31287 for 2021-2025, **2015 is EPSG:3035 -> read CRS per file** |
| FTW predicted         | `https://data.source.coop/ftw/global-data/predictions/vectors/alpha/results-by-admin-conf/admin:country_code=AT/Austria.parquet` | One 298 MB file, 900,048 polygons, 2024 + 2025 together (year via `determination:datetime`). CC-BY-4.0. CRS absent -> OGC:CRS84. The `tge-labs/...` prefix 404s. `features/` holds STAC metadata, COGs, and a Zarr of S2 planting/harvest composites            |

Declared columns: `id`, `crop:code`, `crop:name` (DE), `hcat:code`
(10-digit), `hcat:name`, `hcat:name_en`, `metrics:area`,
`determination:datetime`, `bbox` struct. GeoParquet 1.1 bbox covering,
spatially sorted, 25k-row groups (the AOI touches 2 of 118). The `year`
partition is the edition.

### Field sources — query cost

| Query            | Time  | GETs | Bytes  | Rows in AOI             |
| ---------------- | ----- | ---- | ------ | ----------------------- |
| Declared 2025    | 4.5 s | 11   | 3.4 MB | 371 fields              |
| Declared 2024    | 4.6 s | 12   | 5.6 MB | 354 fields              |
| FTW (both years) | 5.8 s | 26   | 29 MB  | 108 (2024) / 106 (2025) |

Footer/metadata alone is ~2 s + 0.3-0.6 MB per file. FTW has a bbox covering
column but only 14 x 65k-row groups (6 of 14 touched); **without the
bbox-covering predicate FTW reads 247 MB (~8x worse).** Filter on
`bbox.xmin <= ...` in the file's own CRS; `ST_Intersects` alone reads every
geometry.

### Field sources — what is in the AOI (declared 2025, 371 fields, 1,148 ha)

| Crop              | Fields |
| ----------------- | ------ |
| Fallow            | 87     |
| Field vegetables  | 61     |
| Winter soft wheat | 53     |
| Durum             | 34     |
| Potatoes          | 25     |
| Soy               | 19     |
| Maize             | 18     |
| Sugar beet        | 13     |
| Alfalfa           | 9      |

Draft regimes (HCAT longest-prefix): winter_cereal 105, spring_crop 7,
summer_crop 79, grassland_permanent 13, fallow 87, other 80. Declared field
size p25/p50/p75 = 0.35 / 2.4 / 4.5 ha; **26% are < 0.5 ha**. HCAT is coarse in
places: grain / seed / sugar maize share `3301010600`, and vegetables are
season-ambiguous. FTW confidence is 95-99 everywhere — non-discriminative here.

### FTW vs. declared (same AOI)

| Metric                                                  | 2024                       | 2025   |
| ------------------------------------------------------- | -------------------------- | ------ |
| Declared parcels matched 1:1 (IoU > 0.5)                | 15%                        | 12%    |
| ... area-weighted                                       | 23%                        | 19%    |
| Declared parcels mostly inside one FTW polygon          | ~72% (~95% by area)        | same   |
| Declared area covered by the FTW union                  | ~88%                       | ~88%   |
| FTW polygons matched by some declared field (IoU > 0.5) | 40-49%                     | 40-49% |
| Median declared parcels per FTW polygon                 | 2                          | 2      |
| FTW label purity (majority declared label)              | 57-59% HCAT, 66-70% regime |        |

FTW median polygon is 6 ha and 40% exceed 10 ha, vs. a declared median of
2.4 ha. FTW **under-segments**: it finds the right _extent_ (88% coverage, 95%
of declared area sits inside one polygon) but merges neighbouring parcels with
different crops, so a polygon is a 57-70% pure label unit at best.

### Join experiment (`poc_field_embeddings.py`)

Declared parcels rasterised onto the TESSERA grid (10 m inward buffer, fallback
unbuffered; < 5 interior px dropped), per-field per-year mean/std embedding.
Kept 350/371 (2025) and 345/354 (2024); dropped parcels median ~0.17 ha.
**Field-artifact compute: ~1.6 ms/field** (695 fields × 5 years in 1.15 s,
in-memory) — the store read dominates, not the reduction.

**Separability** (fields as units, 5-fold × 5 repeats, ± ~0.01):

| Task (year)                     | Majority | kNN (k=5, cos) | LogReg acc | LogReg macro-F1 |
| ------------------------------- | -------- | -------------- | ---------- | --------------- |
| Season regime, 6 classes (2025) | 0.29     | 0.82           | **0.855**  | 0.67            |
| Season regime, 6 classes (2024) | 0.28     | 0.82           | 0.84       | 0.75            |
| HCAT, 8 classes + rest (2025)   | 0.23     | 0.73           | **0.81**   | 0.83            |
| HCAT, 8 classes + rest (2024)   | 0.23     | 0.75           | 0.80       | 0.81            |

- Per-class F1 (regime): winter_cereal 0.96, summer_crop 0.90, fallow 0.82,
  other 0.81; grassland_permanent 0.37–0.49 and spring_crop 0.20–0.60 are
  **not** separable at n = 7–12. HCAT: maize 0.95, potatoes 0.90, sugar beet
  0.89, soft wheat 0.84 vs durum 0.86.
- Spatially blocked CV (1 km blocks) costs 2–5 points (HCAT 0.81 → 0.76) —
  mild farm/spatial leakage; soft-vs-durum may partly be management signal.
- Fields < 0.5 ha: regime accuracy 0.73–0.77 vs 0.87–0.88 for larger fields.
  Pixel-level logreg with field-grouped folds + field vote ≈ field-level.

**Temporal transfer** (train 2024 → test 2025, logreg): regime 0.79, HCAT 0.75
raw; **subtracting each year's AOI-mean embedding recovers most of the gap**
(0.83 / 0.78). Not parcel memorisation: on parcels whose crop changed
(n = 176) HCAT accuracy is 0.75–0.82.

**Rotation detection** (275 parcels matched 2024↔2025 at IoU > 0.8): cosine
distance as a "crop changed" score has AUC **0.84** raw, **0.90 year-centred**,
0.95 for parcels ≥ 1 ha; regime change AUC 0.86 / 0.91. Median distance:
same crop 0.14, same regime/different crop 0.19, regime changed 0.27.
Within-regime swaps are barely detectable (AUC 0.61–0.71, n = 15). Raw distance
carries a large global year offset (~0.24 median for every year pair) → always
centre per year.

**FTW block splitting** (50 FTW polygons with ≥ 2 declared parcels): k-means on
pixel embeddings, k by silhouette. Median ARI vs declared parcels **0.82 vs 0.13**
for spatial k-means with the same k; embeddings win in 90% of polygons
(Wilcoxon p ≈ 3e-11). ARI 1.0 for 2-parcel blocks, 0.83 for 3–4, 0.66 for ≥ 5;
74% of polygons ARI ≥ 0.5. Silhouette-k equals the true count only 38% of the
time (±1: 62%) and under-counts ≥ 5 parcels. Blocks whose parcels share one
crop still split (ARI 0.95, n = 6) → embeddings see management/phenology, not
just crop.

**Unsupervised archetypes** (k = 6 on 2025 field means): regime purity 0.70
(standardised) vs 0.29 majority, NMI 0.47; fallow and winter cereal separate,
summer crops and "other" blend.

**Caveats:** one ~3×3 km AOI, ~350 fields, rare classes n = 7–12, declared-label
noise, fallow is a catch-all, 2024/2025 are largely the same parcels, no
hyper-parameter tuning (C = 0.1). Treat the numbers as "signal is clearly
there", not as expected production accuracy; P3 must re-validate on several
regions with spatially blocked CV.

## Design implications (for ADR 0003)

1. **Direct `icechunk` + `xarray` is sufficient** (D2). It worked with no
   workaround; `geotessera` was not needed or benchmarked.
2. **Provider hosting and caching.** Run in **us-west-2**, **parallelise
   years** (5 years cost ~2x one year when threaded), and add a **chunk cache**
   (local disk or in-process keyed by `(zone, year, chunk)`): the icechunk
   default re-downloads on every read. Artifact-level caching (D3) still
   applies on top.
3. **Split zone-crossing bboxes per nominal zone** in production (the spike
   raises `NotImplementedError`); overlap is <= 1 tile so each piece reads from
   its own nominal zone without a merge-quality problem.
4. **Declared (harmonized) data is ground truth.** Where it exists it is both
   the field boundary and the training label (D5).
5. **FTW polygons are field _extents_, not label units.** Use them where no
   declarations exist, but infer crop/regime **per pixel or per sub-polygon
   cluster** inside the polygon, and never assign one label to a whole FTW
   polygon. Their confidence score does not help.
6. **Year = calendar year** => winter crops straddle two embeddings. Winter
   cereals sown in autumn Y-1 are captured partly in the Y-1 embedding (sowing
   and emergence) and partly in Y (growth, harvest); the Y embedding is the
   "harvest year" signal but also carries the autumn sowing of the _next_ crop.
   Declared labels are keyed by harvest year, so expect label/embedding
   misalignment for winter crops. In the **southern hemisphere** the calendar
   year cuts the main growing season in half, so season-regime claims there
   need a dedicated treatment (or are out of scope). Every artifact `summary`
   should state the assumed window.
7. **Read QC lazily.** `*_month_covered` and `*_obs_count` cost round-trips,
   not bytes; fetch only when a result needs a confidence statement. Use
   `scales` NaN as the default coverage mask, and check `years_complete`.
8. **Source the license per collection** and record it at ingest (CC-BY-4.0 for
   both FTW sources here; attribution required). Read the CRS per file.
9. **DuckDB >= 1.5 is required** (older versions return geometry as BLOB, no CRS
   typing) and `enable_server_cert_verification` defaults to **false** in 1.5.6,
   so production must set it **true** explicitly.

## Open questions

- **TESSERA license: CC0 vs. CC-BY-SA?** No license appears in the store/group
  attrs, the mirror, the registry README, the S3 explorer, or the Source Coop
  API. The dClimate repo is Apache-2.0 and `geotessera` is MIT, but both cover
  **code only**. The bucket is **not** requester-pays (anonymous GET/LIST work),
  which says nothing about license. The registry says CC-BY-SA and the repo says
  CC0; this must be asked of Cambridge/dClimate. Until then: **private
  per-user artifacts only**, no export or public layer.
- **Throughput and memory** for county-scale jobs (fields/min, peak memory for
  1,000 fields) were not measured from us-west-2.
- **Fraction of target-region fields that straddle a zone seam** is not
  quantified; only the mechanism (overlap <= 1 tile) is.
- **Brute-force cosine latency and the pgvector threshold** were not measured.
- **PCA(3) render in the UI** (Brandenburg viewport) was not exercised; the
  spike only produced `pca_2024.tif` for Marchfeld.
- **Label-transfer accuracy** (held-out year; cross-border) and
  **season-regime separability**: pending the join experiment.
- **HCAT -> regime mapping** is a draft (longest-prefix); several classes
  (maize variants, vegetables) are ambiguous and need review before it is used
  as a training target.
- **Other countries**: only `at` was probed; other harmonized collections have
  different licenses (CC0, CC-BY-SA, DL-DE-\*, CC-BY-NC for `br_conab`).

## What I could and couldn't run in this container

- Ran against **live** data: icechunk open/read, schema + QC inspection,
  YoY/PCA derivation, GeoParquet bbox-pushdown reads for both field sources,
  IoU matching, license searches.
- Latency numbers were taken through the sandbox proxy, outside us-west-2.
  TLS worked with the preset `SSL_CERT_FILE` / `AWS_CA_BUNDLE` for icechunk and
  with the system store / `SET ca_cert_file` for DuckDB; no verification was
  disabled.

## Dependencies the spike used (none added to the backend)

| Script                 | Packages                                                                                                                     |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `poc_tessera_read.py`  | icechunk 2.3.0, zarr 3.4.1, xarray 2026.9.0, numcodecs 0.17.0 (+ pcodec 1.0.4), numpy, pyproj 3.8.0, rasterio 1.5.2, shapely |
| `poc_field_sources.py` | duckdb 1.5.6, pyarrow 26.0.0, geopandas 1.2.0, shapely 2.2.0, pyproj 3.8.0, pandas 3.0.6                                     |

## Out of scope

The production `geo/tessera.py`, zone-split reads, chunk cache, artifact kinds,
the 3-band COG writer, the `fields` `source`/`license` migration, and any
UI work. This spike decides the approach and proves the two read paths.

## How to run the PoCs

Read path (isolated venv; icechunk honours the preset `SSL_CERT_FILE`):

```bash
uv venv --python 3.12 /tmp/venv-tessera
uv pip install --python /tmp/venv-tessera/bin/python \
    icechunk xarray zarr "numcodecs[pcodec]" numpy pyproj rasterio shapely
/tmp/venv-tessera/bin/python \
    apps/backend/spikes/tessera_embeddings/poc_tessera_read.py --out-dir /tmp/tessera_out
```

Writes `pca_2024.tif` (3-band uint8, EPSG:32633) and `aoi_embeddings.npz`.

Field sources (DuckDB >= 1.5 required):

```bash
uv venv --python 3.12 /tmp/venv-fields
uv pip install --python /tmp/venv-fields/bin/python \
    duckdb pyarrow geopandas shapely pyproj
/tmp/venv-fields/bin/python \
    apps/backend/spikes/tessera_embeddings/poc_field_sources.py --out-dir /tmp/fields_out
```

Writes normalised GeoParquet for both sources. Data is anonymous HTTPS on
`data.source.coop`; TLS verification is explicitly on.

The join experiment (`poc_field_embeddings.py`) consumes the outputs of both
scripts (`aoi_embeddings.npz` + the declared/FTW GeoParquet) and additionally
needs `scikit-learn`; see its docstring for venv and arguments (~3 min on 4
cores).
