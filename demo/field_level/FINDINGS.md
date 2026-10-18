# Field-level insights from fused EO layers: findings

Date 2026-10-18 · branch `claude/field-level-insights` · builds on `demo/analysis/INSIGHTS.md` (embedding findings), which is not repeated here.

> **Revision 2 (same day).**
> - **Main-crop choice is now crop-aware** (`cycles_ts.py`). The first version took each year's highest NDVI in DOY 60–300 as the main crop. When a post-harvest catch crop outgrew a weak main crop, the year read as "late peak, no harvest".
>   - Example: `tr-115077081`, 2024: barley peaked at 0.61, the autumn catch crop at 0.67.
>   - Now the main crop is the cycle that peaks inside the declared crop's expected window. Season bounds and harvest use the original, validated rules around that peak.
>   - Effect: harvest-in-window 92.3/93.3/95.9% → 94.6/93.7/94.7%. "No harvest" flags 2.9/3.3/2.7% → 1.5/0.25/0.4%. "Delayed / resown" flags 3.5/6.7/3.5% → 1.7/3.4/2.1%.
>   - Season greenness is now measured between the main cycle's half-amplitude points, which moves some single-field ranks. A3 conclusions hold.
>   - A first attempt that took the steepest drop between two clear scenes as the harvest date was rejected: harvest-in-window fell to 73%, because gradual cereal senescence never produces one large drop.
> - **New:** daily weather (GeoSphere SPARTACUS for Austria, DWD station data for Uckermark), an 11-year crop history (2015–2025), a 2018 temporal hold-out (A1b), the preceding-crop effect (A8), and a weather test of the terrain zones (A4b).
> - **Single-field report:** a visual history of `tr-115077081` (claude.ai artifact, private) applies all of this to one field.

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
- **Weather, daily 1991–2025:**
  - Austria: GeoSphere Austria SPARTACUS v2, a 1 km grid of RR/TN/TX (CC-BY 4.0), at each window centre.
  - Uckermark: DWD station 01869 Grünow, 2.8 km from the window centre.
  - Evapotranspiration is computed with Hargreaves; normals are 1992–2020 (`weather.py`).
  - Open-Meteo is unusable from this egress: it first returned a daily-quota 429, later timed out.
- SoilGrids is reachable but was not integrated (250 m is too coarse for within-field work). Within-field soil truth comes from eBod (AT) and the Bodenschätzung pits (BB); see A9.

**Pipeline.** `run_all.sh` runs `labels → units → tessera_extract → s2_cube → dem → pheno → features → a1…a6 → dossier`. Since revision 2, `cycles_ts.py` runs between `pheno` and `features`. `weather.py`, `history_labels.py`, `a1b_history.py`, `a4b_zone_weather.py` and `a8_preceding.py` are standalone. Derived tables go to `results/*.json`. No imagery is committed (TESSERA licence).

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

### A1b Eleven-year history and a temporal hold-out

**Data.** FTW declarations 2015–2018, tracked onto the same units (`history_labels.py`). About 1,000 units per Austrian year and about 360 in Uckermark.

**TESSERA coverage gap:** the 2017 layer is **empty over both Austrian windows** (valid fraction 0.0). It is present in Uckermark. 2018 is complete everywhere.

**Hold-out.** Every model below was calibrated on 2019–2025 only, so 2018 was never seen.

| | Marchfeld | Traun-Enns | Uckermark |
|---|---|---|---|
| Rotation 2018→2019, AUC (P / R at 0.5) | 0.943 (0.95 / 0.90) | 0.971 (0.98 / 0.93) | 0.934 (0.92 / 0.75) |
| Rotation 2017→2018 | n/a (no TESSERA) | n/a | 0.883 (0.87 / 0.80) |
| Crop group 2018, model trained on 2019+ (majority) | 0.908 (0.35) | 0.905 (0.39) | 0.863 (0.40) |

**Full history vs the 2019+ window.** Units with ≥60% of years declared and ≥80% arable:

| | Marchfeld | Traun-Enns | Uckermark |
|---|---|---|---|
| Same crop ≥3 years running: full history vs 2019+ | 8.0% vs 5.8% | 6.1% vs 4.1% | 13.8% vs 5.6% |
| Cereal share ≥0.6: full history vs 2019+ | 13% vs 10% | 11% vs 8% | **57% vs 85%** |

- A 7-year window understates monoculture runs by about a third in Austria and by half in Uckermark.
- Uckermark's recent five years are more cereal-heavy than its longer record.
- **Dossier use:** show the longest available history.

## A2 S2 phenology (validated against crop type)

**Harvest date vs an a-priori crop calendar.** A harvest counts if it falls inside the crop's reference window ±10 d.
- Inside the window: 94.6% (Marchfeld, n≈4,100), 93.7% (Traun-Enns, n≈5,900), 94.7% (Uckermark, n≈760). Revision 1 had 92.3 / 93.3 / 95.9%.
- Rank correlation of the crop median against the window midpoint: 0.98 / 0.94 / 0.95.
- Marchfeld medians, DOY: winter barley 175, wheat/durum 186–189, potato 250, soy 275, grain maize 291, sugar beet 311.
- Weakest crops:
  - sunflower in Traun-Enns: 35% inside the window (n=17)
  - rapeseed: 82–84% inside
  - sugar beet in Uckermark: 73% inside (n=26)

**Detection rates:**
- A harvest is detected for 88–100% of field-years per crop.
- Two complete cycles: declared multi-crop processing vegetables 56% vs single-culture vegetables 4.7% (Marchfeld n=1,473; precision 0.56, recall 0.56).
- **Caveat:** in Traun-Enns, post-harvest cover crops that peak before November count as a "cycle" (winter cereals 17% two-cycle). So `n_cycles` needs the cover-crop context.

**Winter cover after a summer harvest** (Nov 16–Dec 31 NDVI; green ≥0.5, bare <0.3):

| | Marchfeld | Traun-Enns | Uckermark |
|---|---|---|---|
| n (ambiguous dropped) | 2,406 (936) | 2,730 (533) | 602 (163) |
| Green share | 43% (year range 15–65%) | 86% | 89% |
| Green → still green Jan–Feb, vs bare → green | 62% vs 5% | 63% vs 1% | 98% vs 27% |
| Green split by next-year declaration: cover/catch : autumn-sown | 749 : 168 | 1,632 : 438 | **70 : 343** |
| Embedding probe, leave-one-year-out AUC (balanced acc) | 0.961 (0.90) | 0.892 (0.85) | 0.902 (0.79) |

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
| ICC (null p95) | 0.112 (0.015) | 0.185 (0.012) | 0.077 (0.043) |
| Leave-one-year-out Spearman (other years' mean → this year) | 0.20 | 0.34 | 0.26 |
| Bottom quartile recurs (chance 25%) | 33% | 43% | 33% |
| YoY ρ, **crop changed** / crop same | **0.02** / 0.26 | 0.17 / 0.22 | 0.13 / 0.20 |
| Same-year ρ with nearest other field ≤500 m | 0.14 | 0.23 | 0.35 |

- Peak NDVI persists more than integrated NDVI: ICC 0.16 / 0.23 / 0.25.
- Peak and harvest timing barely persist: ICC 0.00–0.09.
- One reason a field's rank moves between years is the preceding crop (A8), which changes every year under rotation.

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
- **A4b, weather test** (`a4b_zone_weather.py`):
  - The hollow advantage appears in every one of the 19 window-years: mean per-field ρ(vigour, TPI) is −0.08 to −0.21.
  - Its size does not track the spring water balance consistently: ρ across years is −0.39 (Marchfeld), −0.21 (Traun-Enns) and +0.36 (Uckermark), with only n = 7 / 7 / 5 years.
  - So neither seasonal water redistribution nor waterlogging explains it. The likeliest cause is a stable soil property: deeper, colluvial soils collect in hollows. *Unverified* without a soil map.
- **Field-level counter-example** (`tr-115077081`):
  - Its weak lower strip is weakest in the dry springs (2019 −2.1 SD, 2025 −1.9) and least weak after the wet 2023/24 winter (−0.9).
  - That fits low water-holding soil at that spot.
  - Single field, 7 seasons: a hint, not a test.

### A9 Low-performing zones: delineation, hold-out, soil truth and typology

Scripts: `pixel_phases.py`, `soil_ebod.py`, `soil_bb.py`, `a9_zones_deep.py`.

**Zone score.** Within-field z of season-mean NDVI, averaged over arable seasons and smoothed over 3×3 pixels.

**Weak patch.** Connected pixels (≥0.1 ha) in the field's weakest fifth.

**Soil truth (new, external, independent of the satellite data):**
- **Austria:** the national soil map eBod (BFW; 1:25,000 from a 1:10,000 field survey; public vector tiles, free to embed with attribution).
  - Classes used: arable value 1–5, rooting depth 1–5, plant-available water 1–5 (<60 to >300 mm). Code 0 means "strongly varying" and is excluded.
  - Georeferencing check: never-green pixels (roofs, yards) vs mapped area peaks sharply at zero shift in Marchfeld.
- **Brandenburg:** the official soil-survey pits (Bodenschätzung, LBGR WFS-BOGRABLOECHER, free of charge).
  - 532 pits in the window, 450 of them arable.
  - Each pit carries the soil-quality score (Wertzahl, 13–69) and texture.
- Only derived statistics are committed.

| | Marchfeld | Traun-Enns | Uckermark |
|---|---|---|---|
| **Hold-out:** zones from 2019–22 (BB 2019–21) find each later season's weakest fifth, median AUC (rotated-map null) | **0.79** (0.50), n=2,101 field-seasons | **0.82** (0.50), n=2,368 | **0.87** (0.49), n=288 |
| Field-seasons with AUC > 0.6 (null) | 85% (26%) | 87% (31%) | 96% (21%) |
| Hold-out AUC range by crop | 0.69 (field veg) to 0.84 (winter cereal) | 0.81–0.83 | 0.85–0.89 |
| **Soil map:** fields where the better arable-value part is greener | 68% of 712 (p 4e-23), +0.17 SD | 60% of 243 (p 0.002), +0.18 SD | — |
| … higher plant-available water part greener | 66% of 573 (p 2e-14), +0.13 SD | 61% of 193 (p 0.002), +0.22 SD | — |
| … deeper rooting part greener | 66% of 35 (p 0.09) | **74% of 117** (p 1e-7), **+0.47 SD** | — |
| **Soil pits:** within-field ρ (pit score vs soil-quality score) | — | — | **0.38** (208 pits, 12 fields, p 1e-8) |
| … mean soil-quality score of pits inside weak zones vs elsewhere | — | — | **40.6 vs 53.5** (47 vs 165 pits) |
| Weak patches: median size, share of field, NDVI deficit (p10) | 0.21 ha, 5.7%, −0.040 (−0.07) | 0.23 ha, 8.3%, −0.026 (−0.05) | 0.31 ha, 1.2%, −0.043 (−0.09) |
| Share of seasons a patch is in the weakest fifth (median) | 56% | 58% | 64% |

**Typology.** Rules, first match:
1. **edge / headland:** ≥60% of the patch within 30 m of the field edge, and well above the field's own edge share
2. **legacy parcel:** a former separate 2015–18 parcel holds ≥80% of the patch
3. **drought-prone:** deficit grows in dry springs (ρ ≥ 0.5 vs Apr–Jun water balance), or the deficit is late-season dominated
4. **wet / hollow:** deficit grows in wet springs (ρ ≤ −0.5), or low terrain with an early deficit
5. **establishment:** early-season deficit
6. **unexplained**

| Patch share | Marchfeld (n=1,924) | Traun-Enns | Uckermark |
|---|---|---|---|
| edge / headland | 30% | **51%** | 27% |
| drought-prone | 24% | 16% | 29% |
| wet / hollow | 7% | 6% | 12% |
| establishment | 11% | 6% | 11% |
| legacy parcel | 8% | 7% | 7% |
| unexplained | 20% | 15% | 15% |

**Typology vs soil map (internal check).**
- Edge / headland patches sit on the same soil as the rest of their field: arable value −0.03 / −0.04 classes, and nFK lower in 53–57% of cases, about chance. That is what a management effect should look like.
- Drought-prone patches sit on poorer soil: arable value −0.22 / −0.27 classes, nFK lower in 59–63%, and in Traun-Enns 0.21 classes shallower.
- Legacy-parcel patches are also on poorer soil (−0.18 / −0.20).
- Wet / hollow patches are soil-neutral in Traun-Enns. The eBod water class is not ordinal there, and stagnic soils are scattered, so the soil map cannot test this type.
- **Unverified:** the typology is rule-based and has no field-checked labels. The soil comparison supports the edge vs soil split. It does not validate the finer classes.

**Worked example** (`tr-115077081`, field report):
- The weakest fifth splits into two patches with opposite causes:
  - **A (0.94 ha):** weak in dry springs (ρ +0.79), early-season deficit, partly along the headland, on soil mapped as deep and high-value. Suspect compaction.
  - **B (0.56 ha):** weak in wet springs (ρ −0.82), the lowest part of the field, on the eBod unit mapped *wechselfeucht* (stagnic, medium value). Suspect waterlogging.
- An earlier single explanation ("low water-holding soil") was wrong.

**Agent use.** A `low_zones(field_id)` tool should return patches with type, deficit, recurrence and the evidence behind each type (season timing, weather ρ, terrain, soil). It should give the hold-out AUC as its reliability, and frame its output as "where to dig first", not as a diagnosis.

## A5 Anomaly and event screening

**Scores,** per unit-year, as a robust z within class-year:
- whole-year NDVI trajectory deviation
- in-season-only trajectory deviation (class p10 start of season → p90 end of season)
- embedding distance to the class-year centroid

The trajectory and embedding scores correlate at ρ 0.43–0.49.

**Rules,** as a share of arable unit-years:
- low peak (z ≤ −3): 3.6–6.2%
- delayed / resown (peak ≥25 d late and z ≥3): 1.7–3.4%, down from 3.5–6.7% in revision 1
- no main-crop cycle or no harvest: 0.25–1.5%, down from 2.7–3.3%; most revision-1 flags were the catch-crop artefact

**Validation.**
1. **Declared "FIELD VEGETABLES WITHOUT HARVEST"** (Marchfeld n=30 vs 841 harvested): AUC 0.55 (trajectory), 0.54 (no-harvest rule), 0.69 (low peak). The class is administrative and does **not** mark crop failure, so it is unusable as ground truth.
2. **Blinded curve review.** 30 top-2% and 30 random unit-years were shuffled, then labelled before opening the key (`results/marchfeld_a5_blind_labels*.json`). Labels: A = main-season cycle abnormal; B = off-season deviation only.
   - **Whole-year score:** A or B 70% vs 27% random (Fisher p=0.0008). Mostly B: cover crops and pre-sowing green. So this score finds *practice*, not events.
   - **In-season score, vegetable classes excluded:** A 8/30 = 27% (Wilson 14–44%) vs 1/21 = 5% (1–23%), p=0.045.
   - Vegetable classes are useless as peers: their timing is heterogeneous by design.
   - Single rater (the analyst), n=60 per score: an **indicative** result only.
3. **Agreement between screens.** In-season score vs the low-peak rule gives AUC 0.77 / 0.84 / 0.83. Both come from the same NDVI, so this is consistency, not validation.

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

## A8 Preceding crop and sowing window (`a8_preceding.py`)

**Question.** Does a late harvest of the preceding crop, which means late sowing, weaken the following winter cereal? And does a wet winter make it worse?

**Unit-years.** Winter cereals 2020+, where the same unit was declared and harvested the year before.

**Outcome.** Peer z of season greenness (crop × year × 5 km removed). The 95% CIs are bootstrapped over unit-years.

| Preceding crop | Marchfeld | Traun-Enns | Uckermark |
|---|---|---|---|
| Early non-cereal (harvest ≤ DOY 250: rapeseed, peas, potato…) | **+0.56** (0.47–0.65), n=605 | **+0.63** (0.48–0.77), n=293 | **+0.52** (0.38–0.66), n=131 |
| Late row crop (harvest ≥ DOY 260: beet, soy, maize) | −0.26 (−0.33 to −0.18), n=720 | −0.03 (−0.09 to 0.02), n=1,475 | −0.51 (−0.88 to −0.14), n=67 |
| Cereal (rotation penalty) | −0.33 (−0.49 to −0.16), n=241 | −0.15 (−0.30 to −0.01), n=295 | −0.42 (−0.60 to −0.24), n=207 |
| Within late row crops: later harvest → weaker cereal, ρ | −0.22 (p 3e-9) | −0.31 (p 3e-33) | −0.30 (p 0.016) |

- **The late-minus-early gap is negative in all 16 window-years:**
  - Austria: −0.58 to −1.04 SD
  - Uckermark: −0.12 to −2.10 SD
- **Wet-winter amplification is not supported.** Across years, the gap's correlation with Oct–Mar rain is ρ +0.09 / +0.14 / +0.40 (n = 6 / 6 / 4). The largest Traun-Enns gap (−1.04) did fall in the wettest winter of the seven (2023/24, 389 mm, 76th percentile of 1992–2020).
- **Confounding:** "early non-cereal" also brings a nitrogen and disease break, and late maize leaves residue. Only the within-late-row-crop harvest-date gradient isolates timing. Even that gradient may carry soil type, since late harvests sit on heavier land.
- **Agent use:** `practice_screen` and `field_dossier` should report the preceding crop, its harvest date and this expected penalty, before calling a winter cereal "below peers".

## Weather context (`weather.py`, `results/*_weather.json`)

**Most seasons were warmer than the 1992–2020 median.** Growing degree-days (Mar–Oct) were above the median in 17 of 19 window-years; the exceptions are 2021 in both Austrian windows.

| Window | Notable seasons |
|---|---|
| Traun-Enns | Winter 2023/24 at 389 mm (76th percentile). Spring 2025 dry: Apr–Jun water balance at the 14th percentile. |
| Marchfeld | Winter 2023/24 the wettest since 1992 (313 mm). Spring 2025 and 2021 dry. |
| Uckermark | Springs 2020 and 2022 very dry (Apr–Jun rain 68 and 74 mm against a 120 mm median). |

These are the season effects that peer z removes. They are kept for explaining single fields and as covariates for future season-level models. With n = 5–7 years per window, no season-level weather model was fitted.

## A7 "MACI": PLACEHOLDER

> **Pending definition from Julian.** "MACI time series" is not defined in the repo or prior sessions, and it was not guessed. If it is an S2 index, it goes into `geo/indices.py` and `pheno.py`. All 7 needed bands (B02, B03, B04, B05, B08, B11, B12) are already in the window cubes, so the A7 analysis is a re-run: correlation and unique variance vs NDVI/NDRE, and peer and zone signal.

## What is ready for the agent, and what is not

| Signal | Confidence | Basis |
|---|---|---|
| Rotation flag (0.5 rule), crop-group gap-fill | High, 3 regions | A1 |
| Harvest date, winter cover class | High | A2 calendar match 94–95% (crop-aware main cycle); persistence check |
| Preceding-crop / sowing-window effect on winter cereals | High (direction and size), 3 regions | A8; confounded with nitrogen and disease break |
| 11-year history, gap-fill on unseen years | High | A1b 2018 hold-out: group 0.86–0.91, rotation AUC 0.93–0.97 |
| Within-field persistent zones | **High** | A4/A9: hold-out AUC 0.79–0.87 vs 0.50 null; agrees with the soil map (60–74% of fields) and soil pits (ρ 0.38) |
| Zone typology (edge vs soil-driven vs weather-sensitive) | Medium | A9: edge patches soil-neutral, drought-prone patches on poorer soil; finer classes unverified |
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
- Uckermark has ~50% `unknown` FTW labels and only 5 years with S2 (9 with labels).
- The TESSERA 2017 layer is missing over Austria.
- Weather: one point per window (1 km grid or a station), not per field.

See `TOOL_PROPOSALS.md` for the agent tools and `dossier.schema.json` + `dossiers/*.json` for the worked examples.
