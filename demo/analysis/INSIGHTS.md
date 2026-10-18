# What the TESSERA embeddings tell us — Marchfeld, 2019–2025

Data: TESSERA v1.1 annual 128-d embeddings over a 58 km² window (lon 16.54–16.66, lat 48.22–48.29), 724k px/year.
Labels: Austrian IACS declarations (`ftw/harmonized-field-data`, HCAT classes), ~1,500–1,800 parcels/year, 7,947 parcel-years in 28 classes ≥40 samples.
Unit: parcel mean embedding after a 10 m inward buffer, ≥5 px. "Centred" = minus that year's mean over the whole window.
Scripts: `parcels_years.py` (labels) → `extract.py` (embeddings, run with the backend venv on `feat/tessera-p1`) → `analyse.py`.

## 1. Crop type is linearly decodable, and it transfers to unseen years

Logistic regression on parcel means, **leave-one-year-out** (train on 6 years, predict the 7th):

| Target | Accuracy | Macro-F1 | Majority baseline |
|---|---|---|---|
| 28 fine crops, raw | 0.803 | 0.676 | 0.165 |
| 28 fine crops, year-centred | **0.831** | 0.715 | 0.165 |
| 7 crop groups, year-centred | **0.941** | 0.905 | 0.328 |

- Random 5-fold CV, which mixes years, reaches 0.855. Cross-year transfer therefore costs only about 2 points, so the embedding space is stable year to year.
- Per held-out year, accuracy is 0.79–0.85 with no trend.
- **Implication:** last year's declarations are enough to map this year's crops before the declarations are published.

**Strong classes (recall ≥0.9):** sugar beet 0.94, green fallow 0.93, winter soft wheat 0.90, soybeans 0.90, winter barley 0.90, sunflowers 0.91, greenhouse 0.99.

**Weak classes:**
- Spelt 0.32, triticale 0.38: small winter cereals that are absorbed into wheat.
- "Other forage" 0.10 and "other farm area" 0.31: catch-all labels.
- Early potatoes 0.29.

**Top confusions are mostly use or market distinctions, not biological ones:**
- durum ↔ soft wheat (196)
- edible ↔ industry potatoes (138)
- processing ↔ fresh vegetables (121)

These are effectively a label-noise ceiling: no remote-sensing model can separate them.

## 2. The main axes are phenology (consistent with "when is the field green")

PCA on year-centred parcel means (explained variance 26 / 17 / 11 %). Each line orders the crop groups by their mean score:

- **PC1:** fallow/forage −3.6 < winter cereal −2.4 < spring cereal < maize < field veg < legume/oilseed +4.0 < root crop +4.7. Covered over winter vs bare until late spring.
- **PC2:** winter cereal −2.7 … fallow/forage +2.9. Harvested in July vs green into autumn.
- **PC3:** maize −2.8 isolated. A late, tall C4 canopy in Aug–Sep.

So the embedding behaves like a compressed annual phenology and structure signature. That explains what it can and cannot see (§3).

## 3. Rotation detection works with an absolute threshold, contrary to the current docstring

Units: the 2024 parcel geometries, tracked over 2019–2025 and labelled each year by the parcel that overlaps ≥80% of the unit. 6,320 consecutive-year pairs, 78% of which changed crop (Marchfeld rotates hard).

| Detector | AUC |
|---|---|
| raw cosine distance | 0.909 |
| **centred cosine distance** | **0.955** |
| centred, arable only | 0.951 |
| centred, arable only, excluding fallow→fallow | 0.930 |

| Centred threshold | Precision | Recall | FPR |
|---|---|---|---|
| 0.3 | 0.931 | 0.965 | — |
| 0.4 (arable) | 0.949 | 0.936 | 0.20 |
| **0.5 (arable)** | **0.965** | **0.895** | **0.13** |
| 0.7 | 0.983 | 0.768 | — |

**Distribution:**
- Centred distance, unchanged pairs: p10 / p50 / p90 = 0.07 / 0.17 / 0.54.
- Centred distance, changed pairs: 0.49 / 0.96 / 1.30.
- Best Youden threshold: 0.49.
- This matches the 4-parcel spot check in REPORT.md (fallow 0.12–0.24, rotations 0.86–1.46).

**Blind spots:**
- *Rotations it misses* are phenology-alike swaps: wheat → barley, wheat → rye, durum ↔ soft wheat, soy → maize. The detector measures a change in phenology, not a change of species.
- *Unchanged pairs that look changed:* processing vegetables 0.54, alfalfa 0.42 (cut schedules), turf 0.46. These are management-driven.
- *Most stable:* greenhouses 0.04, orchards ~0.1, fallow 0.16.

**Implication for #71 (fixes B3):** drop "no fixed cut-off" from the docstring. Report `rotation_likely = centred ≥ 0.5`, describe the result as a "phenology change", and say that same-family cereal swaps are invisible to it.

## 4. Year centring is justified

- The window-mean embedding shifts 2.0–2.6 (L2) between consecutive years.
- The closest pair of crop centroids is only 1.04 apart (median 6.45).
- So the year offset is as large as the gap between similar crops. Centring adds about 3 points of crop accuracy and +0.05 rotation AUC.
- Caveat: centring on a 1 km window around each field (the backend default) versus the whole 58 km² window was not compared here.

## 5. Other usable signals

- **"Fields like this one":** cosine kNN restricted to *other* years has precision@10 for the same fine crop of 0.67 (chance 0.09). That makes a viable similar-field search or analogue-finder.
- **Declaration anomalies:** 2.0% of parcel-years get P(declared group) < 0.05 from the leave-one-year-out model. The top patterns are:
  - declared field veg that looks like maize (17), plausibly sweetcorn or mis-coded
  - declared spring cereal that looks like winter cereal (12)
  - declared soy that looks like vegetables (12)

  These are candidates for checks-by-monitoring-style review, but **unverified**: they still need imagery or NDVI confirmation.
- **Within-field heterogeneity:** mean pixel-to-parcel-mean distance is highest for sugar beet, soy, winter barley and grain maize (2.99–3.27) and lowest for fallow and seed maize (~2.3). This hints at management-zone potential for row crops; not explored further.

## Limits

- One region, one agro-system (irrigated Pannonian arable land).
- Labels are declarations, which carry their own noise.
- Calendar-year embeddings: winter crops straddle two years (sown in autumn of Y−1).
- The fixed-unit rotation analysis assumes 2024 parcel shapes hold back to 2019; units whose largest overlapping parcel covers <80% of them were dropped.
- The TESSERA license (CC0 vs CC-BY-SA) is unresolved, so no imagery is included here.

## 6. Two crop cycles in one season (2024)

Ground truth comes from Sentinel-2 L2A NDVI rather than declarations (`s2_ndvi.py`, `cycles.py`):
- 45 dates in 2024; SCL classes 4–5 count as clear; per-parcel mean NDVI.
- A parcel-date is kept if ≥80% of its pixels are clear.
- The series is interpolated to 5-day steps and smoothed (Savitzky–Golay).
- 1,257 parcels have usable series.
- Embedding probes use 2-km spatial-block cross-validation.

| Definition | Share of parcels | AUC, declared crop only | AUC, embedding only |
|---|---|---|---|
| ≥2 NDVI peaks (≥0.5, prominence ≥0.2) anywhere in the calendar year | 38% | 0.77 | **0.97** |
| ≥2 **complete** in-season cycles (each peaks Mar–Oct and declines before year end) | 8% | 0.72 | **0.91** |

- **The loose definition is mostly *winter green after harvest*, not a second crop.** For wheat the median second "peak" is 15 Dec, at the end of the series. That is either a cover crop or next season's autumn-sown crop emerging.
  - Within a single crop the embedding still separates it almost perfectly: durum AUC 0.995, soft wheat 0.985.
  - So *post-harvest cover / autumn sowing* is a practice the embeddings encode very well.
  - Telling cover crop from next season's winter crop needs the next year's declaration.
- **The strict definition is true double cropping.**
  - Timing patterns: spring + late summer (48), spring + summer (42), summer + autumn (12).
  - Declared "processing vegetables, multi-cultured" parcels are 81% two-cycle, against 0–9% for every other crop. That independently validates the NDVI labelling.
  - The embedding finds double-cropped parcels much better than the crop label does (AUC 0.91 vs 0.72). Balanced accuracy at p = 0.5 is 0.71 because of the 8% prevalence, so the threshold should be tuned.
- **Caveat:** TESSERA is itself trained on S1/S2 time series, so this shows the 128-d vector *retains* intra-season cycle structure. The NDVI labels are not independent evidence of anything new. The practical gain is cost: one read per pixel-year instead of ~45 scenes.

## 7. Over-winter cover after harvest: cover/catch crop vs next season's autumn-sown crop (2024)

Script: `winter_cover.py`.

**Population.** Harvested arable parcels only: the main NDVI peak is ≥0.5 by early September, followed by a trough below 0.35. Perennials, fallow and greenhouses are excluded.

**Classes,** from mean NDVI between mid-November and the end of December:
- **winter green:** ≥0.45
- **bare:** <0.30
- parcels in between are dropped

**Splitting winter green.** The 2025 declaration on the same ground (≥80% overlap) decides which kind each winter-green parcel is:
- **autumn-sown next crop:** the 2025 crop is a winter crop
- **cover/catch crop:** the 2025 crop is a spring/summer crop

**Counts.** 680 parcels: 493 bare and 187 winter green. The 187 split into 129 cover/catch, 34 autumn-sown next crop, and 9 that go to perennial/fallow.

**Independent sanity check from timing:** the autumn green-up date (NDVI ≥0.4) for cover/catch crops has median 16 Oct (IQR 6–31 Oct); for autumn-sown next crops it has median 20 Nov (IQR 15–25 Nov). This fits catch crops sown right after the cereal harvest versus winter cereals sown in October.

**Practice prevalence** among harvested parcels:

| 2024 crop | bare | cover/catch | next winter crop |
|---|---|---|---|
| durum | 0.62 | 0.35 | 0.00 |
| soft wheat | 0.64 | 0.30 | 0.02 |
| field veg | 0.81 | 0.08 | 0.10 |
| grain maize | 0.74 | 0.07 | 0.07 |
| soy | 0.94 | 0.03 | 0.02 |

A third of cereal fields carry a cover crop. Late-harvested row crops almost never do.

**Embedding probes** (2024 embedding only, 2-km spatial-block CV):

| Task | n | Prevalence | AUC, crop label | AUC, embedding | Balanced accuracy |
|---|---|---|---|---|---|
| winter green vs bare after harvest | 680 | 0.28 | 0.615 | **0.996** | 0.964 |
| cover/catch vs autumn-sown next crop | 163 | 0.79 | 0.834 | **0.972** | 0.889 |

The embedding beats the hand-made NDVI green-up date (AUC 0.883) at separating cover crops from autumn sowings. It keeps more than greening timing, possibly canopy density or radar-visible structure; unverified.

**Caveats:**
- "Cover/catch" here means green over winter followed by a spring crop. Volunteer cereals or weedy stubble would land in the same class.
- The labels depend on 2025 declarations, so they reflect what was declared, not what was observed.

## 8. Cross-year transfer of the practice detectors (2023 ↔ 2024)

Script: `xyear.py`. Labels are rebuilt from scratch for each year from that year's Sentinel-2 NDVI: 46 dates in 2023, 45 in 2024. The classifier is logistic regression on year-centred embeddings with balanced class weights, trained on one year and applied unchanged to the other.

| Task | Train → test | AUC | Balanced accuracy | Precision | Recall |
|---|---|---|---|---|---|
| winter green after harvest | 2023 → 2024 | **0.995** | 0.951 | 0.802 | 0.995 |
| winter green after harvest | 2024 → 2023 | **0.952** | 0.850 | 0.932 | 0.745 |
| double crop (2 complete cycles) | 2023 → 2024 | 0.860 | 0.752 | 0.256 | 0.680 |
| double crop (2 complete cycles) | 2024 → 2023 | 0.880 | 0.801 | 0.455 | 0.735 |

- **Winter cover transfers almost losslessly.** The ranking holds across years, so it is deployable as a screening layer for any TESSERA year.
- **Double cropping transfers with a drop:** AUC goes from 0.91 within-year to 0.86–0.88. Precision at the default threshold is poor because prevalence shifts between years.
- **The prevalence shift itself:**
  - Double crop: 13.1% in 2023 vs 8.2% in 2024.
  - Winter green: 45% vs 28%.
  - The shift could reflect real year differences (autumn moisture, sowing windows) or be an artefact of cloud-limited Nov–Dec observations in the NDVI labels. Not resolved here. For deployment, calibrate the threshold per year, e.g. on a small NDVI-labelled sample, or report a ranked probability rather than a yes/no.
