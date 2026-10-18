# Handoff — field-level insights from every available data layer

Paste everything below the line into a new Claude Code session on `julianblue/geogent`.

---

## Mission

Build **field-level insights** by fusing every data layer we can reach for a set of real agricultural fields. The output is a per-field **dossier**: what was grown, how it was managed, how it performed against its peers, where it varies inside the field, and what is anomalous. Every claim must be validated against ground truth or a control.

"Highly useful" means an agronomist or the geogent agent could act on it. "This field's NDVI peaked at 0.81" is not enough. "Late harvest, no cover crop, 14% below same-crop peers on cumulative greenness, with a persistent low-vigour zone in the NE corner across 4 of 5 seasons" is the target.

## Start here (read before doing anything)

1. Root `CLAUDE.md` and `CONTEXT.md`, then `apps/backend/CLAUDE.md`. Also read `docs/adr/0002-satellite-data-cubes-management-zones.md` (data cubes, field memory) and `docs/roadmap/satellite-data-cubes.md`.
2. Prior work, on branch `claude/new-session-bhzwoc`:
   - `demo/analysis/INSIGHTS.md`: the embedding findings. Build on them, don't redo them.
   - `demo/analysis/*.py`: working pipelines to reuse.
   - `demo/REPORT.md`: stack bugs and the environment gotchas below.
3. TESSERA code lives on PR #71, branch `feat/tessera-p1`: `apps/backend/src/geogent_backend/geo/tessera.py` provides `IcechunkTesseraReader.read_window(bbox, years, dim)`. **Do not push to `feat/tessera-p1` or `feat/tessera-embeddings-spike`**; other sessions own them. Use a `git worktree` to import from them.
4. Notion knowledge base (Notion MCP), Platform & Geospatial Cockpit:
   - Read "Knowledge base: read me first" for the conventions.
   - Read the Knowledge entry "TESSERA embeddings: empirical findings (Marchfeld + Upper Austria)".
   - Read the roadmap item "Open EO embeddings (TESSERA / AlphaEarth)".
5. **Ask Julian at the start:** what "MACI time series" refers to. It is not defined in the repo or in prior sessions. Candidates:
   - a vegetation index (e.g. MCARI or another chlorophyll/anthocyanin index)
   - a specific internal product or time-series service
   - something else

   Don't guess. If it is an S2 index, add it to `apps/backend/src/geogent_backend/geo/indices.py` alongside NDVI/NDRE/NDMI/EVI/SAVI/NBR/NDWI/MNDWI.

## Data layers (and how to reach them)

**1. Fields of The World (FTW), source.coop `ftw/`, anonymous HTTPS, GeoParquet with a `bbox` covering column.** Use DuckDB ≥1.5 with `enable_server_cert_verification=true` and `ca_cert_file='/root/.ccr/ca-bundle.crt'`.
- `harmonized-field-data/<cc>/year=YYYY/<cc>-YYYY.parquet`: declared parcels with crop labels (`crop:name`, HCAT `hcat:name_en`/`hcat:code`) per year.
  - Austria (`at`) covers 2019–2025 and is proven. Other countries exist; list them.
  - Filter on `bbox.xmin/...` in the **file's CRS** (EPSG:31287 for AT).
  - See `demo/analysis/parcels_years.py`.
- `global-data/predictions/vectors/...`: model-predicted field boundaries (no crop). Use it to compare against declared boundaries (boundary disagreement, unregistered fields, splits and merges).

**2. TESSERA v1.1 annual 128-d embeddings, 10 m, 2017–2025.**
- Source: anonymous Icechunk `s3://tessera-embeddings/v1.1/dclimate.icechunk`, us-west-2.
- Read with the reader above, using the backend venv (`uv sync --all-groups` installs icechunk/xarray/zarr).
- About 19 s per year for a 58 km² window.
- See `demo/analysis/extract.py`.

**3. Sentinel-2 L2A time series**, Element84 earth-search STAC, `sentinel-2-l2a`.
- Use `pystac-client` and rasterio COG window reads. Mask clouds with SCL classes 4/5, and read SCL with `out_shape` = the 10 m band shape.
- See `demo/analysis/s2_ndvi.py`.
- Also available through the backend: the `seasonal_index_time_series_for_field` path. **Known cap:** `max_scenes=60` truncates a multi-year request to its first year. Query per year.

**4. Data cubes / field memory (ADR 0002, `geo/cube.py`, multi-collection S2 + Landsat with reflectance scaling, #65).**
- Builds a `(time, y, x)` cube per field on one canonical grid.
- Field-memory artifacts give multi-season per-pixel layers for within-field zoning.
- Use them for within-field variability and zone stability.

**5. "MACI" time series:** see question 5 above.

**6. Optional context layers (add if reachable, note the license):**
- Copernicus DEM GLO-30 (slope, aspect, TWI) for zone explanation
- Open-Meteo / ERA5 daily weather (GDD, precipitation, heat/drought stress windows)
- SoilGrids (texture, SOC)

Check that each host is reachable through the proxy first:

```
curl -sS "$HTTPS_PROXY/__agentproxy/status"
```

On a 403, report the blocked host; do not work around it.

## What is already known (from the embedding work)

- Embeddings encode annual phenology:
  - crop type: 83% over 28 classes, cross-year; 85% cross-region
  - rotation: centred YoY cosine ≥ 0.5, AUC 0.95–0.97, portable across regions
  - winter cover after harvest: AUC ≥ 0.95 across years and regions
  - double cropping: AUC 0.81–0.91, needs a local threshold
  - similar-field search: P@10 0.67
  - ~2% declaration anomalies
- **Center by the year's AOI mean** before comparing years. This is neutral for cross-region transfer.
- Embeddings say *which field, which year*. Time series say *when and what*. Use embeddings to screen, and S2/cubes to explain and confirm.

## Analyses to run (prioritise; each needs a validation or control)

Pick 2–3 study windows of ~50 km²: Marchfeld (lon 16.54–16.66, lat 48.22–48.29), Traun-Enns plateau (lon 14.38–14.50, lat 48.12–48.19), plus one non-Austrian FTW country for contrast. Per field and year, build a feature table, then:

1. **Crop history and rotation profile (7 years):**
   - declared sequence, embedding-based rotation flags, rotation diversity
   - cereal share, monoculture runs
   - disagreements between declaration and embedding
2. **Phenology metrics from S2:**
   - start/peak/end of season, peak value, season length
   - integrated greenness (proxy for biomass and yield potential)
   - harvest date, number of cycles, winter cover, bare-soil days (erosion and nitrate risk)
   - Validate harvest and cycle detection against crop type and declared multi-crop classes.
3. **Peer benchmarking:** each field against same-crop, same-year fields within ~5 km on integrated greenness and peak timing, as a percentile. Separate field effects from season effects; check persistence across years.
4. **Within-field variability (cubes / field memory):**
   - per-pixel multi-season zones
   - zone stability across years (do the same low zones recur?)
   - fraction of the field in persistent low vigour
   - Exclude 1-pixel edges. Explain zones with DEM/TWI if available.
5. **Anomaly and event screening:**
   - field-vs-peer deviation in embedding space and in the NDVI trajectory, per year
   - candidate crop failure, resowing, abandonment, waterlogging
   - Validate against FTW "without harvest" classes, or against a held-out manual check of NDVI curves.
6. **Boundary quality:** FTW predicted vs declared polygons (IoU, splits, merges, unregistered fields). This matters for every field-level metric.
7. **"MACI"** once defined: what it adds beyond NDVI/NDRE (correlation, unique variance, any agronomic signal).

## Deliverables

- `demo/field_level/` on a new branch `claude/field-level-insights`, branched from `main`:
  - scripts
  - `FINDINGS.md`: dense; every number with n, method and validation
  - a per-field dossier JSON schema plus 3–5 worked example dossiers
- A short list of **agent tool proposals** for geogent, for example `field_dossier(field_id)`, `peer_benchmark`, `practice_screen` and `zone_stability`. Give inputs and outputs, and which validated signal backs each one.
- File a ≤1-page Research report in Notion Knowledge, following the read-me conventions:
  - Source, Source date, Source link
  - Tags: geospatial, roadmap
  - Link it to the roadmap item and to the existing TESSERA findings entry.

## Environment gotchas (learned the hard way)

- **No Docker daemon by default:** run `dockerd &`. PostGIS image: `postgis/postgis:16-3.4`.
- **Ports 2024/2025 are taken** by sandbox infra. Run langgraph on 2124 and set the UI's `LANGGRAPH_URL`.
- **Backend `.env.example` bug:** `CORS_ORIGINS` must be JSON (`["http://localhost:3000"]`).
- **seed_user** rejects `.local` emails; use `@example.com`. The agent's `BACKEND_SERVICE_EMAIL` must equal the UI login.
- **DuckDB:** if a query on a timestamp column fails, also `pip install pytz`.
- **Isolated scratch venvs:** keep scratch venvs out of the app venvs. Run downloaded data with `python -I`.
- **Never** disable TLS verification. The proxy CA is `/root/.ccr/ca-bundle.crt`, and `SSL_CERT_FILE` / `AWS_CA_BUNDLE` are preset.
- **Scratch output is ephemeral:** the scratchpad is wiped between sessions. Commit scripts and small derived tables, not raw rasters.
- **TESSERA license** (CC0 vs CC-BY-SA) is unresolved. **Do not publish or commit derived imagery.** Commit numbers and tables only.
- Commit with conventional commits. Keep PNGs local, or add them to `.git/info/exclude`.

## Method guardrails

- Spatial-block CV (2 km blocks) and leave-one-year-out for anything learned.
- Report baselines: declared-crop-only, chance, majority.
- Prefer peer-relative over absolute thresholds, except where an absolute threshold was shown to be portable (rotation 0.5).
- Calendar-year embeddings split winter crops across two years. Account for that in rotation and phenology.
- State n, prevalence and confidence for every claim. Flag unverified hypotheses explicitly.
