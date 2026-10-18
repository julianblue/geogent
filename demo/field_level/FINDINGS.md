# Field-level insights from fused EO layers: findings

Date 2026-10-18 · branch `claude/field-level-insights` · builds on `demo/analysis/INSIGHTS.md` (embedding findings), which is not repeated here.

## Setup

| Window | Area | Labels | Units (≥0.5 ha) | Unit-years with S2 phenology | S2 clear obs / unit-year (median) |
|---|---|---|---|---|---|
| Marchfeld (AT, irrigated Pannonian) | 58 km² | FTW `at` 2019–25, EuroCrops AT 2021 | 1,234 | 7,174 | 44 |
| Traun-Enns (AT, rainfed) | 50 km² | FTW `at` 2019–25, EuroCrops AT 2021 | 1,333 | 8,098 | 44 |
| Uckermark (DE-BB, large-field) | 95 km² | FTW `de_bb` 2019–23 (no 2024/25), EuroCrops DE-BB 2023 | 477 | 1,959 | 34 |

**Unit.** The latest declared parcel, tracked back through the years. A year's label is the parcel covering ≥80% of the unit; otherwise the year is "untracked" (split, merge or undeclared). Units are buffered 10 m inward, which drops the edge pixel.

**Layers, all on one 10 m UTM grid.** TESSERA and the S2 cube share the same origin, so no resampling is needed.
- TESSERA v1.1, 128-d, year-centred.
- S2 L2A window cube: earth-search, one scene per day, SCL 4/5. A unit-date counts if ≥80% of its pixels are clear. The series is resampled to a 5-day grid and Savitzky–Golay smoothed.
- Copernicus GLO-30 DEM (slope, TPI over 150 m, D8 TWI).
- FTW PRUE predicted boundaries.
- Weather (Open-Meteo) was **not used**: the shared egress hit a daily quota (HTTP 429). SoilGrids is reachable but was not integrated.

**Pipeline.** `run_all.sh` runs `labels → units → tessera_extract → s2_cube → dem → pheno → features → a1…a6 → dossier`. Derived tables go to `results/*.json`. No imagery is committed (TESSERA licence).

**Data gotcha (not a stack bug).** earth-search `sentinel-2-l2a` items with `earthsearch:boa_offset_applied=true` hold pixels with the BOA offset already removed. Dense-canopy red DN p0.1 is 110–270. Yet STAC `raster:bands` still advertises `offset −0.1`. `geo/collections.py` (`offset=0`) is **correct**. A client that honours `raster:bands` (odc-stac, stackstac) shifts reflectance by −0.1, and NDVI goes past 1 on dark pixels: my first pass hit exactly this.

## A1 Crop history and rotation (7 years AT, 5 years BB)

| | Marchfeld | Traun-Enns | Uckermark |
|---|---|---|---|
| Consecutive declared pairs (n, % changed) | 5,701 (79%) | 6,591 (80%) | 1,496 (46%) |
| AUC, centred YoY distance vs declared change | **0.958** | **0.975** | **0.930** |
| P / R / FPR at the 0.5 rule | 0.97 / 0.90 / 0.12 | 0.98 / 0.92 / 0.07 | 0.94 / 0.75 / 0.04 |
| Misses that are same-group swaps | 33% | 39% | **67%** (wheat→barley ×73) |
| LOYO crop-group accuracy (gap-fill) | 0.915 (majority 0.32) | 0.946 (0.35) | 0.899 (0.37) |
| Untracked unit-years filled by embedding | 1,030 / 1,098 | 967 / 1,010 | 216 / 281 |
| Arable units: cereal share ≥0.6 | 11% | 9% | **85%** |
| Arable units: same crop ≥3 consecutive years | 5.6% | 3.8% | 5.3% |
| Units with ≥2 declaration–phenology disagreements | 11% | 6% | 13% |

- The 0.5 rule transfers to a third, non-Austrian region at precision 0.94.
- Recall drops where rotations are cereal-on-cereal, which is the known blind spot.
- **Dossier use:** report the declared sequence, fill untracked years with the embedding group (labelled "inferred"), and attach disagreements as review items.
- *Unverified:* whether disagreements mark declaration errors or management changes. Only the curve review in A5 touches this.

## A2 S2 phenology (validated against crop type)

**Harvest date vs an a-priori crop calendar.** A harvest counts if it falls inside the crop's reference window ±10 d.
- Inside the window: 92.3% (Marchfeld, n≈3,800), 93.3% (Traun-Enns, n≈5,700), 95.9% (Uckermark, n≈740).
- Rank correlation of the crop median against the window midpoint: 0.97 / 0.94 / 1.00.
- Marchfeld medians, DOY: winter barley 176, wheat/durum 186–191, potato 246, soy 271, grain maize 286, sugar beet 311.
- Outlier: sunflower in Traun-Enns, 29% inside the window (n=17).

**Detection rates:**
- A harvest is detected for 88–100% of field-years per crop.
- Two complete cycles: declared multi-crop processing vegetables 56% vs single-culture vegetables 4.7% (Marchfeld n=1,473; precision 0.56, recall 0.56).
- **Caveat:** in Traun-Enns, post-harvest cover crops that peak before November count as a "cycle" (winter cereals 17% two-cycle). So `n_cycles` needs the cover-crop context.

**Winter cover after a summer harvest** (Nov 16–Dec 31 NDVI; green ≥0.5, bare <0.3):

| | Marchfeld | Traun-Enns | Uckermark |
|---|---|---|---|
| n (ambiguous dropped) | 2,266 (872) | 2,499 (498) | 594 (160) |
| Green share | 42% (year range 15–65%) | 85% | 89% |
| Green → still green Jan–Feb, vs bare → green | 63% vs 4% | 63% vs 2.5% | 98% vs 23% |
| Green split by next-year declaration: cover/catch : autumn-sown | 688 : 160 | 1,449 : 416 | **59 : 346** |
| Embedding probe, leave-one-year-out AUC (balanced acc) | 0.963 (0.90) | 0.914 (0.88) | 0.914 (0.82) |

- The Uckermark "winter green" is mostly the next autumn-sown crop (rapeseed is sown in August); in Austria it is mostly catch crops.
- The 2025 Marchfeld figure (15% green) and the 2024 one (32%) coincide with sparse December scenes. **Unverified:** whether that is a real practice shift or a gap artefact.

**Bare-soil days per year** (smoothed NDVI <0.3, with an observation within 20 days). This is a proxy for erosion and nitrate-leaching exposure, and it has not been validated against any ground truth. Winter cereals are the least exposed everywhere:

| | Winter cereals | Maize | Vegetables |
|---|---|---|---|
| Marchfeld (median days) | 140 | 215 | 225 |
| Traun-Enns | 85 | 150 | 105 |
| Uckermark | 80 | 155 | n/a |

## A3 Peer benchmarking: a real but mostly one-season signal

**Method.** Peers are the same declared class, same year, within 5 km, ≥5 fields. z_peer is a robust z score, which removes the crop × season × neighbourhood effect. Persistence is tested with the ICC across years against a permutation null (z shuffled across units within year, 200 draws).

| Seasonal integrated NDVI (z_peer) | Marchfeld | Traun-Enns | Uckermark |
|---|---|---|---|
| ICC (null p95) | 0.108 (0.015) | 0.154 (0.012) | 0.155 (0.044) |
| Leave-one-year-out Spearman (other years' mean → this year) | 0.19 | 0.30 | 0.24 |
| Bottom quartile recurs (chance 25%) | 33% | 42% | 34% |
| YoY ρ, **crop changed** / crop same | **0.03** / 0.26 | 0.18 / 0.16 | 0.07 / 0.20 |
| Same-year ρ with nearest other field ≤500 m | 0.16 | 0.24 | 0.21 |

- Peak NDVI persists more than integrated NDVI: ICC 0.16 / 0.23 / 0.30.
- Peak and harvest timing barely persist: ICC 0.03–0.09.

**Reading.**
- A field's standing against its peers is mostly a season outcome.
- A persistent *field* effect exists, but it is small. In irrigated Marchfeld it does not carry across a crop change. In rainfed Traun-Enns it does (ρ 0.18). **Hypothesis:** irrigation masks soil differences; rainfed soil water capacity shows through.
- Neighbour correlation is about the size of own-field persistence, so part of the "field effect" is local soil or landscape, not management.
- **Consequence:** dossiers show the multi-year percentile series and call a field persistently weak only on repeated bottom-quartile years. Example: `tr-115552306` sits in the bottom quartile 7 of 7 years, p≈6e-5 per field, still significant across ~1,000 fields.
- iNDVI as a yield proxy is **unvalidated here** (no yield data).

## A4 Within-field variability (cube / field memory)

**Method.**
- Per pixel and year: season-mean NDVI over the unit's in-season clear dates, z-scored within the unit. This is the `geo/cube.py` productivity reducer made peer-relative.
- Units used: arable, ≥30 px, ≥3 seasons.

| | Marchfeld | Traun-Enns | Uckermark |
|---|---|---|---|
| Units (median seasons, px) | 923 (7, 302) | 994 (7, 238) | 176 (5, 1,084) |
| Year-to-year pattern ρ, median (IQR) | 0.34 (0.23–0.47) | 0.43 | **0.54** |
| Same after removing the distance-to-edge effect | 0.35 | 0.42 | 0.53 |
| Split-half ρ (odd vs even years) | 0.58 | 0.67 | 0.73 |
| Field share low (bottom 20%) in ≥60% of seasons, mean (chance) | 9.6% (2.1%) | 10.4% (1.8%) | 15.5% (5.6%) |
| Units with ≥10% persistent low | 44% | 53% | 96% |
| Median relief inside the unit | 1.6 m | 5.6 m | 11.4 m |
| Units where vigour is higher on low TPI (rotated-DEM null) | 75% (51%) | 64% (45%) | 77% (49%) |
| Units with positive vigour–TWI ρ (null) | 82% (51%) | 69% (53%) | 89% (48%) |

- Zones recur across years and crops, and they are not an edge artefact.
- The direction is consistent across all three windows: **depressions and wetter positions are greener**. This is water redistribution in water-limited systems.
- Per-field terrain ρ is modest (median |ρ| 0.13–0.30, against nulls of 0.07–0.26). Marchfeld relief is at DEM error level.
- **Unverified:** soil texture (SoilGrids is too coarse at 250 m for within-field work) and waterlogging. A low-lying zone that is *low* vigour in wet years would be the waterlogging signature; it was not tested because there is no weather data.

## A5 Anomaly and event screening

**Scores,** per unit-year, as a robust z within class-year:
- whole-year NDVI trajectory deviation
- in-season-only trajectory deviation (class p10 start of season → p90 end of season)
- embedding distance to the class-year centroid

The trajectory and embedding scores correlate at ρ 0.43–0.49.

**Rules,** as a share of arable unit-years:
- low peak (z ≤ −3): 3.3–5.3%
- delayed / resown (peak ≥25 d late and z ≥3): 3.5–6.7%
- no harvest signal: 2.7–3.3%

**Validation.**
1. **Declared "FIELD VEGETABLES WITHOUT HARVEST"** (Marchfeld n=30 vs 841 harvested): AUC 0.55 (trajectory), 0.54 (no-harvest rule), 0.69 (low peak). The class is administrative and does **not** mark crop failure, so it is unusable as ground truth.
2. **Blinded curve review.** 30 top-2% and 30 random unit-years were shuffled, then labelled before opening the key (`results/marchfeld_a5_blind_labels*.json`). Labels: A = main-season cycle abnormal; B = off-season deviation only.
   - **Whole-year score:** A or B 70% vs 27% random (Fisher p=0.0008). Mostly B: cover crops and pre-sowing green. So this score finds *practice*, not events.
   - **In-season score, vegetable classes excluded:** A 8/30 = 27% (Wilson 14–44%) vs 1/21 = 5% (1–23%), p=0.045.
   - Vegetable classes are useless as peers: their timing is heterogeneous by design.
   - Single rater (the analyst), n=60 per score: an **indicative** result only.
3. **Agreement between screens.** In-season score vs the low-peak rule gives AUC 0.76 / 0.83 / 0.90. Both come from the same NDVI, so this is consistency, not validation.

**Example.** `uc-68109`: winter barley 2021 at peak z ≤ −3 with off-peer spring vigour, then declared "withdrawn from production" in 2022–23. This is a plausible failure → abandonment story, unverified.

## A6 Boundary and label quality

**FTW PRUE predicted vs declared** (same year, interior parcels ≥0.5 ha):

| | Marchfeld 2024 / 2025 | Traun-Enns 2024 / 2025 | Uckermark (pred 2024 vs decl 2023) |
|---|---|---|---|
| Median best IoU | 0.19 / 0.18 | 0.27 / 0.24 | 0.00 |
| IoU ≥0.5 | 18% | 31% | 18% |
| Predictions merging ≥2 parcels | 217 of 410 | 225 of 596 | 37 of 123 |
| Declared area covered by predictions | 85% / 82% | 85% / 86% | 67% |
| Predicted area with no declaration | 0.1–0.2% | 0.1–0.2% | 0% |

- PRUE delineates **field blocks**: adjacent strip parcels with different crops merge.
- IoU rises with parcel size (ρ 0.47 Marchfeld, 0.31 Traun-Enns).
- There are essentially no unregistered fields.
- In Traun-Enns, split parcels have higher TESSERA dispersion (n=7, Mann-Whitney p=0.0008), so they may be real two-management units. The sample is too small to act on.

**EuroCrops vs FTW harmonized, same country-year:**
- **AT 2021:** identical geometry (IoU 1.0 for all 1,475 / 2,588 parcels, same AMA source). HCAT code agreement 97.0% / 99.1%. Every disagreement is a code-version mapping: summer cereals `…02` in FTW vs `…03` in EuroCrops. Plus one **EuroCrops semantic error**: AT "TURF" (lawn) mapped to `peat_turf` (3307).
- **DE-BB 2023:** 86% of parcels at IoU ≥0.9.
  - FTW labels 524/1,072 parcels `unknown` (3399).
  - EuroCrops leaves 440/1,132 unmapped.
  - Where both are labelled (n=490), agreement is 99%.
- **Licence:** the Zenodo record 10118572 says **CC-BY-SA-4.0**, not CC-BY-4.0 as the handoff states.

## A7 "MACI": PLACEHOLDER

> **Pending definition from Julian.** "MACI time series" is not defined in the repo or prior sessions, and it was not guessed. If it is an S2 index, it goes into `geo/indices.py` and `pheno.py`. All 7 needed bands (B02, B03, B04, B05, B08, B11, B12) are already in the window cubes, so the A7 analysis is a re-run: correlation and unique variance vs NDVI/NDRE, and peer and zone signal.

## What is ready for the agent, and what is not

| Signal | Confidence | Basis |
|---|---|---|
| Rotation flag (0.5 rule), crop-group gap-fill | High, 3 regions | A1 |
| Harvest date, winter cover class | High | A2 calendar match 92–96%; persistence check |
| Within-field persistent zones | Medium-high | A4: edge-controlled, binomial null, split-half 0.58–0.73 |
| Terrain explanation of zones | Medium, direction only | A4 rotated-DEM null |
| Peer percentile (single year) | Medium as "this season"; **low** as a field trait | A3 |
| Event screen (failure, resowing) | Low, a review queue | A5, 27% precision |
| PRUE boundaries as management units | Low in strip landscapes | A6 |

## Limits

- Labels are declarations.
- There is no yield or ground truth for events.
- Single rater in A5.
- Calendar-year phenology: winter-crop establishment sits in year Y−1's autumn. `winter_late`/`winter_early` bridge it only partly.
- Cloud gaps in Nov–Feb.
- The DEM is a DSM (it includes hedges and buildings near edges).
- Uckermark has ~50% `unknown` FTW labels and only 5 years.

See `TOOL_PROPOSALS.md` for the agent tools and `dossier.schema.json` + `dossiers/*.json` for the worked examples.
