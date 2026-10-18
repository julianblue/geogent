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
