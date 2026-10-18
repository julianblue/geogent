# Agent tool proposals (geogent)

Each tool follows ADR 0002: heavy layers stay server-side as content-addressed artifacts; the agent gets a handle plus a compact summary. "Backing" names the validated result in `FINDINGS.md`; "Must say" is the caveat the docstring has to force into the answer (lesson from B3/B5 in `demo/REPORT.md`).

| Tool | Inputs | Output (summary) | Backing (FINDINGS §) | Must say |
|---|---|---|---|---|
| `field_dossier(field_id, years?)` | field id; default all TESSERA/declaration years | the `dossier.schema.json` object: history, rotation profile, management, peer performance, within-field zones, screen flags, boundary note, narrative | all sections; each block carries `evidence` keys | Untracked years are *inferred*; flags are screens, not findings. |
| `crop_history(field_id)` | field id | per year: declared crop, embedding group (LOYO), P(declared), centred YoY distance, `phenology_change = d ≥ 0.5`, disagreements | A1: rotation AUC 0.958 / 0.975 / Uck; group gap-fill acc 0.915–0.946 | Same-family cereal swaps (wheat↔barley/rye) and soy↔maize are invisible (33–39% of misses). |
| `practice_screen(field_id, year)` | field, year | main-crop cycle chosen inside the declared crop's window (`cycles_ts.py`), plus cover / catch cycles; harvest DOY, winter cover class (green/bare/ambiguous) and kind (cover/catch vs autumn-sown, needs the next-year declaration), bare-soil days, preceding crop with its harvest date and expected penalty | A2: harvest within the crop window 94–95%; cycles vs multi-crop class; winter-cover embedding LOYO AUC 0.89–0.96; A8: preceding-crop effect | Never take the year's NDVI maximum as the main crop: catch crops can outgrow a weak main crop. A winter cereal after a late row crop is expected 0.6–1 SD below one after rapeseed or peas, so report this before calling it weak. |
| `peer_benchmark(field_id, year, metric="indvi_season")` | field, year, metric ∈ {indvi_season, peak_ndvi, peak_doy, harvest_doy} | percentile and robust z vs same-crop/same-year fields ≤5 km (n peers), the field's multi-year percentile series, plus the season's weather percentiles (SPARTACUS/DWD) | A3: ICC 0.11–0.23 (null p95 ≤0.015) | **One-season signal.** Persistence across crop changes is ≈0 in Marchfeld and 0.18 in Traun-Enns; never call a field "chronically poor" from one year. |
| `zone_stability(field_id, years?)` | field, ≥3 arable seasons | artifact: multi-season within-field z map and persistent-low mask (COG); summary: stability ρ, split-half ρ, % persistent low vs chance, low-zone direction, terrain ρ vs rotated-DEM null | A4: stability ρ 0.34–0.43, unchanged after the edge control; persistent-low 9.6–10.4% vs ~2% chance | Explain zones with terrain only where ρ exceeds the rotated null; Marchfeld relief (~1.6 m) is within DEM error. |
| `anomaly_screen(aoi or field_ids, year)` | AOI/fields, year | ranked list: in-season trajectory deviation z, embedding deviation z, rule events (crop_failure, delayed_resown, no_harvest) | A5: blinded review, in-season score top-2% → 27% main-season abnormal (non-veg) vs 5% random | Exclude vegetable classes as peers (heterogeneous timing). Off-season deviation is practice (cover crop), not an event. Unverified against ground truth. |
| `boundary_check(field_id)` | field | best IoU vs FTW PRUE prediction, block ratio, split flag | A6 | PRUE delineates *field blocks*. IoU <0.5 in ~70–80% of Austrian strip parcels; this is not a declaration error. |

## Order to build

1. `crop_history` + `practice_screen`: highest validated accuracy, cheap (one TESSERA read per year, plus the per-year S2 series the backend already computes). Fixes B3 and B5 directly.
2. `zone_stability`: extends `geo/cube.py` (already a productivity reducer) with the within-field z, multi-season stack and edge buffer.
3. `peer_benchmark`: needs a peer index (declared parcels + same-year metrics), i.e. the FTW/EuroCrops ingest into `fields`.
4. `field_dossier`: composes 1–3; `anomaly_screen` and `boundary_check` as optional blocks.

## Contract notes

- Every numeric answer carries `n`, the reference set (peers, years) and a validation pointer; the agent prompt forbids absolute adjectives ("poor", "excellent") without a percentile.
- S2 reflectance: keep `offset=0` for earth-search `sentinel-2-l2a` (pixels already harmonised). Do **not** switch to the STAC `raster:bands` offset (−0.1); that inflates NDVI past 1 on dark targets.
- Query S2 per year (B5): the `max_scenes=60` cap truncates multi-year requests.
