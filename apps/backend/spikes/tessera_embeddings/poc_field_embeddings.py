"""PoC: do field-level TESSERA embeddings carry crop / season signal? (join of two spikes)

Spike for the TESSERA-embeddings / deep-analysis work. NOT production code — no FastAPI wiring,
no caching, no registry. It joins the outputs of the two sibling spikes:

  * ``poc_tessera_read.py``   -> ``aoi_embeddings.npz``  (5 years x 128 bands, 10 m, EPSG:32633)
  * ``poc_field_sources.py``  -> ``declared_{2024,2025}.parquet`` (INVEKOS parcels, crop labels)
                                 ``ftw_{2024,2025}.parquet``      (FTW predicted field blocks)

and answers, with numbers and honest error bars, whether the embeddings are useful for the three
backend tools we are considering (``field_embedding_profile``, ``classify_fields``, boundary QA):

  1. **Field-level embedding artifact** — rasterise each parcel onto the embedding grid (10 m
     inward buffer, fall back to no buffer if that leaves nothing), drop fields with < 5 interior
     pixels, and compute per-field per-year mean / std embedding + pixel count. Timed.
  2. **Crop / season-regime separability** — stratified 5-fold CV over *fields* (repeated, kNN
     k=5 cosine and standardised logistic regression, majority baseline), declared labels of year
     Y on year-Y embeddings (2024 and 2025), for ``season_regime`` and top-N HCAT classes. Also a
     spatially-blocked CV (neighbouring parcels share farmers / soils / management) and a
     pixel-level CV with folds grouped by field (no leakage between pixels of one field).
  3. **Temporal transfer** — train on 2024 labels + 2024 embeddings, test on 2025 (all fields,
     physically-matched parcels, and parcels with no 2024 counterpart), vs within-year CV.
  4. **Rotation detection** — match parcels across the 2024/2025 editions (IoU > 0.8); does the
     cosine distance between the two field-mean embeddings predict "declared crop changed"?
     Prints the 2021-2025 year-over-year distance series for three example parcels.
  5. **FTW block splitting** — for FTW 2025 polygons that contain >= 2 declared parcels, k-means
     (k = 2..4 by silhouette) on the polygon's pixel embeddings; agreement with declared parcel
     membership (adjusted Rand index) vs a spatial-only k-means baseline.
  6. **Unsupervised archetypes** — k-means (k=6) on 2025 field means vs ``season_regime``.
  7. Writes ``field_embeddings_{2025,2024}.parquet`` (labels, pixel count, mean/std vectors),
     ``results.json`` and two PNGs.

Everything is evaluated on ONE small AOI (Marchfeld, ~3.4 x 3.0 km) with ~350 parcels per year, so
treat every number as indicative, not as a benchmark; the repeated-CV standard deviations only
capture split noise, not sampling noise. Labels are declared (not surveyed) and the FTW polygons
are a coarse prediction.

Run (isolated venv, deps NOT added to the backend project; consumes the outputs of the two
sibling spikes):

    uv venv --python 3.12 /tmp/venv-join
    uv pip install --python /tmp/venv-join/bin/python \\
        numpy rasterio geopandas pyarrow scikit-learn shapely pyproj scipy matplotlib
    /tmp/venv-join/bin/python apps/backend/spikes/tessera_embeddings/poc_field_embeddings.py \\
        --embeddings /tmp/tessera_out/aoi_embeddings.npz \\
        --fields-dir /tmp/fields_out --out-dir /tmp/join_out

Runtime is ~1-3 min on 4 cores (dominated by the pixel-level CV). ``--no-plots`` skips matplotlib.
Licences: the parcel / FTW data are CC-BY-4.0 (see ``poc_field_sources.py``); TESSERA see
``poc_tessera_read.py``.
"""

from __future__ import annotations

import argparse
import json
import time
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import shapely
from affine import Affine
from rasterio.features import rasterize
from scipy import stats
from shapely import STRtree
from shapely.geometry import box
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    adjusted_rand_score,
    f1_score,
    normalized_mutual_info_score,
    roc_auc_score,
    silhouette_score,
)
from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

MIN_PIXELS = 5  # fields with fewer interior pixels are dropped
INWARD_BUFFER_M = 10.0  # one pixel: keeps edge (mixed) pixels out of the field statistics
MIN_CLASS_FIELDS_HCAT = 8  # HCAT classes with fewer fields (in either year) merge into "_rest"
MIN_CLASS_FIELDS_REGIME = 5  # >= n_splits so every class can appear in every stratified fold
N_SPLITS = 5
N_REPEATS = 5  # repeated stratified CV with different shuffles
SPATIAL_BLOCKS_M = (500.0, 1000.0)  # block edges for the spatially-blocked CV
PIXELS_PER_FIELD = 100  # pixel-level CV: max pixels sampled per field
KNN_K = 5
LR_C = 0.1  # fixed (no tuning on the test folds); 128 features vs ~350 samples needs shrinkage
IOU_MATCH = 0.8
ARCHETYPE_K = 6
FTW_MIN_PIXELS = 40
FTW_K_RANGE = (2, 3, 4)
SILHOUETTE_SAMPLE = 1500
REST = "_rest"
SEED = 0

REGIME_COLOURS = {  # colour-blind-safe (Okabe-Ito)
    "winter_cereal": "#E69F00",
    "summer_crop": "#009E73",
    "spring_crop": "#56B4E9",
    "fallow": "#999999",
    "grassland_permanent": "#0072B2",
    "other": "#CC79A7",
}


# --------------------------------------------------------------------------------------------
# Grid + rasterisation
# --------------------------------------------------------------------------------------------


@dataclass
class Grid:
    transform: Affine
    height: int
    width: int
    crs: str
    years: list[int]
    emb: np.ndarray  # (Y, 128, H, W) float32

    @property
    def bounds_box(self) -> Any:
        x0, y0 = self.transform * (0, self.height)
        x1, y1 = self.transform * (self.width, 0)
        return box(x0, y0, x1, y1)

    def flat(self, year: int) -> np.ndarray:
        """(H*W, 128) view of one year (rows are pixels, row-major like the raster)."""
        yi = self.years.index(year)
        return self.emb[yi].reshape(self.emb.shape[1], -1).T


def load_grid(path: Path) -> Grid:
    z = np.load(path)
    emb = z["embeddings"]
    return Grid(
        transform=Affine(*[float(v) for v in z["transform"]]),
        height=emb.shape[2],
        width=emb.shape[3],
        crs=str(z["crs"]),
        years=[int(y) for y in z["years"]],
        emb=emb,
    )


def pixel_indices(geom: Any, grid: Grid) -> np.ndarray:
    """Flat (row-major) indices of the pixels whose centre lies inside ``geom`` (clipped to grid)."""
    empty = np.empty(0, dtype=np.int64)
    if geom is None or geom.is_empty:
        return empty
    inv = ~grid.transform
    minx, miny, maxx, maxy = geom.bounds
    c0, r1 = inv * (minx, miny)
    c1, r0 = inv * (maxx, maxy)
    col0, col1 = max(int(np.floor(c0)), 0), min(int(np.ceil(c1)) + 1, grid.width)
    row0, row1 = max(int(np.floor(r0)), 0), min(int(np.ceil(r1)) + 1, grid.height)
    if col1 <= col0 or row1 <= row0:
        return empty
    sub = grid.transform * Affine.translation(col0, row0)
    mask = rasterize(
        [(geom, 1)], out_shape=(row1 - row0, col1 - col0), transform=sub, fill=0, dtype="uint8"
    )
    rr, cc = np.nonzero(mask)
    return ((rr + row0) * grid.width + (cc + col0)).astype(np.int64)


def interior_pixels(
    geom: Any, grid: Grid, buffer_m: float = INWARD_BUFFER_M
) -> tuple[np.ndarray, bool]:
    """Pixels inside ``geom`` shrunk by ``buffer_m``; falls back to no buffer if that is empty."""
    idx = pixel_indices(geom.buffer(-buffer_m), grid) if buffer_m > 0 else np.empty(0, np.int64)
    if idx.size:
        return idx, True
    return pixel_indices(geom, grid), False


def finite_pixels(grid: Grid) -> np.ndarray:
    """(H*W,) bool: pixels whose 128-d vector is finite in every loaded year (NaN = no coverage)."""
    return np.logical_and.reduce([np.isfinite(grid.flat(y)).all(axis=1) for y in grid.years])


# --------------------------------------------------------------------------------------------
# Step 1: field-level embedding artifact
# --------------------------------------------------------------------------------------------


@dataclass
class FieldSet:
    year: int
    gdf: gpd.GeoDataFrame  # kept fields, projected; column ``orig`` = row in the raw edition
    pix: list[np.ndarray]  # flat pixel indices per kept field
    mean: np.ndarray  # (n, Y, 128)
    std: np.ndarray  # (n, Y, 128)
    n_px: np.ndarray  # (n,)
    buffered: np.ndarray  # (n,) bool: inward buffer applied (False = fallback)
    coverage: np.ndarray  # (n,) share of the parcel area inside the embedding grid
    full: gpd.GeoDataFrame  # all parcels of the edition (projected), incl. dropped
    dropped: pd.DataFrame


def load_declared(path: Path, crs: str) -> gpd.GeoDataFrame:
    gdf = gpd.read_parquet(path).to_crs(crs).reset_index(drop=True)
    bad = ~gdf.geometry.is_valid
    if bad.any():
        gdf.loc[bad, "geometry"] = gdf.loc[bad, "geometry"].buffer(0)
    return gdf


def build_field_set(gdf: gpd.GeoDataFrame, grid: Grid, year: int) -> FieldSet:
    flats = [grid.flat(y) for y in grid.years]
    finite = finite_pixels(grid)
    grid_box = grid.bounds_box
    keep_rows, pix, buf, cov, dropped = [], [], [], [], []
    for i, geom in enumerate(gdf.geometry.values):
        idx, buffered = interior_pixels(geom, grid)
        idx = idx[finite[idx]]  # drop NaN (no-coverage) pixels before the minimum-count check
        if idx.size < MIN_PIXELS:
            dropped.append({"orig": i, "area_m2": float(geom.area), "n_px": int(idx.size)})
            continue
        keep_rows.append(i)
        pix.append(idx)
        buf.append(buffered)
        cov.append(float(geom.intersection(grid_box).area / geom.area))
    kept = gdf.iloc[keep_rows].copy()
    kept["orig"] = keep_rows
    kept = kept.reset_index(drop=True)
    n, n_years = len(kept), len(grid.years)
    mean = np.empty((n, n_years, 128), dtype=np.float32)
    std = np.empty_like(mean)
    for yi in range(n_years):
        for j, idx in enumerate(pix):
            v = flats[yi][idx].astype(np.float64)
            mean[j, yi] = v.mean(axis=0)
            std[j, yi] = v.std(axis=0)
    return FieldSet(
        year=year,
        gdf=kept,
        pix=pix,
        mean=mean,
        std=std,
        n_px=np.array([p.size for p in pix]),
        buffered=np.array(buf),
        coverage=np.array(cov),
        full=gdf,
        dropped=pd.DataFrame(dropped, columns=["orig", "area_m2", "n_px"]),
    )


# --------------------------------------------------------------------------------------------
# Evaluation helpers
# --------------------------------------------------------------------------------------------


def shared_classes(label_sets: list[pd.Series], min_n: int) -> set[str]:
    keep: set[str] | None = None
    for s in label_sets:
        ok = set(s.value_counts()[lambda c: c >= min_n].index)
        keep = ok if keep is None else keep & ok
    return keep or set()


def merge_rare(s: pd.Series, keep: set[str]) -> np.ndarray:
    return np.array([v if v in keep else REST for v in s.astype(str)], dtype=object)


def model_factories() -> dict[str, Any]:
    return {
        "majority": lambda: DummyClassifier(strategy="most_frequent"),
        "knn5_cos": lambda: KNeighborsClassifier(
            n_neighbors=KNN_K, metric="cosine", algorithm="brute"
        ),
        "logreg": lambda: make_pipeline(
            StandardScaler(), LogisticRegression(C=LR_C, max_iter=3000)
        ),
    }


def cv_predictions(
    feats: np.ndarray,
    y: np.ndarray,
    factory: Any,
    seeds: list[int],
    groups: np.ndarray | None = None,
) -> list[np.ndarray]:
    out = []
    for seed in seeds:
        if groups is None:
            it = StratifiedKFold(N_SPLITS, shuffle=True, random_state=seed).split(feats, y)
        else:
            it = StratifiedGroupKFold(N_SPLITS, shuffle=True, random_state=seed).split(
                feats, y, groups
            )
        oof = np.empty(len(y), dtype=object)
        for tr, te in it:
            m = factory()
            m.fit(feats[tr], y[tr])
            oof[te] = m.predict(feats[te])
        out.append(oof)
    return out


def summarise(y: np.ndarray, preds: list[np.ndarray], classes: list[str]) -> dict[str, Any]:
    acc = [float(np.mean(p == y)) for p in preds]
    f1m = [float(f1_score(y, p, labels=classes, average="macro", zero_division=0)) for p in preds]
    f1c = np.array([f1_score(y, p, labels=classes, average=None, zero_division=0) for p in preds])
    return {
        "acc": float(np.mean(acc)),
        "acc_sd": float(np.std(acc)),
        "macro_f1": float(np.mean(f1m)),
        "macro_f1_sd": float(np.std(f1m)),
        "f1_per_class": {c: float(v) for c, v in zip(classes, f1c.mean(axis=0), strict=True)},
    }


def fmt_row(name: str, r: dict[str, Any]) -> str:
    return (
        f"    {name:<22s} acc {r['acc']:.3f}±{r['acc_sd']:.3f}  "
        f"macroF1 {r['macro_f1']:.3f}±{r['macro_f1_sd']:.3f}"
    )


def print_per_class(classes: list[str], counts: dict[str, int], res: dict[str, Any]) -> None:
    head = "      " + "".join(f"{m:>11s}" for m in res)
    print(f"    per-class F1 (n fields){head.strip():>40s}")
    for c in classes:
        cells = "".join(f"{res[m]['f1_per_class'][c]:>11.2f}" for m in res)
        print(f"      {c[:28]:<28s} ({counts[c]:>3d}){cells}")


# --------------------------------------------------------------------------------------------
# Step 2: separability
# --------------------------------------------------------------------------------------------


def label_tasks(fsets: dict[int, FieldSet]) -> dict[str, dict[str, Any]]:
    """Shared class maps so within-year CV and 2024->2025 transfer use identical label spaces."""
    tasks: dict[str, dict[str, Any]] = {}
    for task, col, min_n in (
        ("regime", "season_regime", MIN_CLASS_FIELDS_REGIME),
        ("hcat", "hcat_name", MIN_CLASS_FIELDS_HCAT),
    ):
        keep = shared_classes([fs.gdf[col] for fs in fsets.values()], min_n)
        labels = {yr: merge_rare(fs.gdf[col], keep) for yr, fs in fsets.items()}
        classes = sorted(set().union(*[set(v) for v in labels.values()]))
        tasks[task] = {"labels": labels, "classes": classes, "col": col}
    return tasks


def separability(
    fsets: dict[int, FieldSet], grid: Grid, tasks: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    seeds = list(range(SEED, SEED + N_REPEATS))
    for year in sorted(fsets):
        fs = fsets[year]
        yi = grid.years.index(year)
        feats = fs.mean[:, yi]
        feats_ms = np.concatenate([fs.mean[:, yi], fs.std[:, yi]], axis=1)
        cx, cy = fs.gdf.geometry.centroid.x.values, fs.gdf.geometry.centroid.y.values
        block_ids = {
            edge: np.floor((cx - cx.min()) / edge).astype(int) * 1000
            + np.floor((cy - cy.min()) / edge).astype(int)
            for edge in SPATIAL_BLOCKS_M
        }
        for task, spec in tasks.items():
            y = spec["labels"][year]
            classes = spec["classes"]
            counts = {c: int(np.sum(y == c)) for c in classes}
            facs = model_factories()
            res: dict[str, Any] = {}
            for name, fac in facs.items():
                res[name] = summarise(y, cv_predictions(feats, y, fac, seeds), classes)
            res["logreg+std"] = summarise(
                y, cv_predictions(feats_ms, y, facs["logreg"], seeds), classes
            )
            spatial = {
                f"{int(edge)}m/{name}": summarise(
                    y, cv_predictions(feats, y, facs[name], seeds, blocks), classes
                )
                for edge, blocks in block_ids.items()
                for name in ("majority", "knn5_cos", "logreg")
            }
            # accuracy by parcel size (logreg, repeat-averaged)
            lr_preds = cv_predictions(feats, y, facs["logreg"], seeds)
            small = fs.gdf.area_m2.values < 5000
            by_size = {
                "lt_0.5ha": float(np.mean([np.mean(p[small] == y[small]) for p in lr_preds])),
                "ge_0.5ha": float(np.mean([np.mean(p[~small] == y[~small]) for p in lr_preds])),
                "n_lt_0.5ha": int(small.sum()),
                "n_ge_0.5ha": int((~small).sum()),
            }
            out[f"{year}/{task}"] = {
                "n_fields": len(y),
                "classes": counts,
                "field_cv": res,
                "field_cv_spatial_blocks": spatial,
                "logreg_acc_by_size": by_size,
            }
            print(f"\n  [{year}] {task}: n={len(y)} fields, {len(classes)} classes")
            for name, r in res.items():
                print(fmt_row(name, r))
            print(
                "    -- spatially blocked CV; blocks: "
                + ", ".join(f"{int(e)} m -> {len(set(b))}" for e, b in block_ids.items())
            )
            for name, r in spatial.items():
                print(fmt_row(name, r))
            print(f"    logreg acc by size: {by_size}")
            print_per_class(
                classes, counts, {k: res[k] for k in ("majority", "knn5_cos", "logreg")}
            )
    return out


def pixel_level_cv(
    fsets: dict[int, FieldSet], grid: Grid, tasks: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    rng = np.random.default_rng(SEED)
    for year in sorted(fsets):
        fs = fsets[year]
        flat = grid.flat(year)
        sel = [rng.choice(p, size=min(PIXELS_PER_FIELD, p.size), replace=False) for p in fs.pix]
        groups = np.concatenate([np.full(s.size, j) for j, s in enumerate(sel)])
        x = flat[np.concatenate(sel)].astype(np.float32)
        for task, spec in tasks.items():
            y_field = spec["labels"][year]
            classes = spec["classes"]
            y = y_field[groups]
            facs = model_factories()
            res: dict[str, Any] = {}
            print(f"\n  [{year}] {task}: {len(y)} pixels from {len(sel)} fields (grouped folds)")
            for name, fac in facs.items():
                pred = cv_predictions(x, y, fac, [SEED], groups)[0]
                pix = summarise(y, [pred], classes)
                vote = np.array(
                    [pd.Series(pred[groups == j]).mode().iloc[0] for j in range(len(sel))],
                    dtype=object,
                )
                fld = summarise(y_field, [vote], classes)
                res[name] = {
                    "pixel_acc": pix["acc"],
                    "pixel_macro_f1": pix["macro_f1"],
                    "field_vote_acc": fld["acc"],
                    "field_vote_macro_f1": fld["macro_f1"],
                }
                print(
                    f"    {name:<10s} pixel acc {pix['acc']:.3f} macroF1 {pix['macro_f1']:.3f} | "
                    f"field-vote acc {fld['acc']:.3f} macroF1 {fld['macro_f1']:.3f}"
                )
            out[f"{year}/{task}"] = res
    return out


# --------------------------------------------------------------------------------------------
# Step 3 + 4: matching, transfer, rotation
# --------------------------------------------------------------------------------------------


def match_editions(a: gpd.GeoDataFrame, b: gpd.GeoDataFrame, min_iou: float) -> pd.DataFrame:
    """Mutual-best IoU matches between two editions (rows are positions in a / b)."""
    ga, gb = a.geometry.values, b.geometry.values
    ia, ib = STRtree(gb).query(ga, predicate="intersects")
    inter = shapely.area(shapely.intersection(ga[ia], gb[ib]))
    union = shapely.area(ga[ia]) + shapely.area(gb[ib]) - inter
    df = pd.DataFrame({"ia": ia, "ib": ib, "iou": inter / union})
    best_a = df.loc[df.groupby("ia").iou.idxmax()].set_index("ia").ib
    best_b = df.loc[df.groupby("ib").iou.idxmax()].set_index("ib").ia
    good = df[df.iou > min_iou]
    mutual = [
        (r.ia, r.ib, r.iou)
        for r in good.itertuples()
        if best_a.get(r.ia) == r.ib and best_b.get(r.ib) == r.ia
    ]
    return pd.DataFrame(mutual, columns=["ia", "ib", "iou"]).astype({"ia": int, "ib": int})


def cosine_dist(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    num = np.sum(a * b, axis=-1)
    den = np.linalg.norm(a, axis=-1) * np.linalg.norm(b, axis=-1)
    return 1.0 - num / den


def temporal_transfer(
    fsets: dict[int, FieldSet],
    grid: Grid,
    tasks: dict[str, dict[str, Any]],
    matches: pd.DataFrame,
    within: dict[str, Any],
) -> dict[str, Any]:
    f24, f25 = fsets[2024], fsets[2025]
    i24, i25 = grid.years.index(2024), grid.years.index(2025)
    to_kept24 = {o: k for k, o in enumerate(f24.gdf.orig)}
    to_kept25 = {o: k for k, o in enumerate(f25.gdf.orig)}
    m = [
        (to_kept24[a], to_kept25[b])
        for a, b in zip(matches.ia, matches.ib, strict=True)
        if a in to_kept24 and b in to_kept25
    ]
    matched25 = np.zeros(len(f25.gdf), dtype=bool)
    matched25[[b for _, b in m]] = True
    # Leakage control: on parcels whose declared crop CHANGED 2024->2025, a model that merely
    # recognised the physical parcel from the 2024 training set would predict the old crop.
    changed25 = np.zeros(len(f25.gdf), dtype=bool)
    for a, b in m:
        changed25[b] = f24.gdf.hcat_code.iloc[a] != f25.gdf.hcat_code.iloc[b]
    subsets = {
        "all_2025": np.ones(len(f25.gdf), dtype=bool),
        "matched": matched25,
        "unmatched": ~matched25,
        "matched_crop_changed": changed25,
        "matched_crop_same": matched25 & ~changed25,
    }
    out: dict[str, Any] = {"n_matched_kept": int(matched25.sum())}
    variants = {
        "raw": (f24.mean[:, i24], f25.mean[:, i25]),
        "year_centred": (
            f24.mean[:, i24] - f24.mean[:, i24].mean(axis=0),
            f25.mean[:, i25] - f25.mean[:, i25].mean(axis=0),
        ),
    }
    for task, spec in tasks.items():
        ytr, yte = spec["labels"][2024], spec["labels"][2025]
        classes = spec["classes"]
        out[task] = {}
        print(
            f"\n  {task}: train 2024 (n={len(ytr)}) -> test 2025 "
            f"(n={len(yte)}; matched {int(matched25.sum())}, unmatched {int((~matched25).sum())})"
        )
        for vname, (xtr, xte) in variants.items():
            for name, fac in model_factories().items():
                if vname == "year_centred" and name == "majority":
                    continue
                mdl = fac()
                mdl.fit(xtr, ytr)
                pred = mdl.predict(xte)
                for sname, mask in subsets.items():
                    r = summarise(yte[mask], [pred[mask]], classes)
                    key = f"{vname}/{name}/{sname}"
                    out[task][key] = {
                        "acc": r["acc"],
                        "macro_f1": r["macro_f1"],
                        "n": int(mask.sum()),
                    }
                a, b = out[task][f"{vname}/{name}/all_2025"], out[task][f"{vname}/{name}/matched"]
                c = out[task][f"{vname}/{name}/unmatched"]
                d1 = out[task][f"{vname}/{name}/matched_crop_changed"]
                d2 = out[task][f"{vname}/{name}/matched_crop_same"]
                print(
                    f"    {vname:<12s} {name:<9s} all acc {a['acc']:.3f} F1 {a['macro_f1']:.3f} | "
                    f"matched {b['acc']:.3f} (n={b['n']}) [crop changed {d1['acc']:.3f} "
                    f"(n={d1['n']}), same {d2['acc']:.3f} (n={d2['n']})] | "
                    f"unmatched {c['acc']:.3f} (n={c['n']})"
                )
        w = within[f"2025/{task}"]["field_cv"]
        print(
            f"    within-2025 CV for comparison: majority {w['majority']['acc']:.3f}  "
            f"knn5 {w['knn5_cos']['acc']:.3f}  logreg {w['logreg']['acc']:.3f}"
        )
    return out


def auc_with_ci(y: np.ndarray, score: np.ndarray, n_boot: int = 1000) -> tuple[float, float, float]:
    auc = float(roc_auc_score(y, score))
    rng = np.random.default_rng(SEED)
    boots = []
    for _ in range(n_boot):
        s = rng.integers(0, len(y), len(y))
        if y[s].min() == y[s].max():
            continue
        boots.append(roc_auc_score(y[s], score[s]))
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return auc, float(lo), float(hi)


def rotation(fsets: dict[int, FieldSet], grid: Grid, matches: pd.DataFrame) -> dict[str, Any]:
    f24, f25 = fsets[2024], fsets[2025]
    i24, i25 = grid.years.index(2024), grid.years.index(2025)
    to_kept24 = {o: k for k, o in enumerate(f24.gdf.orig)}
    to_kept25 = {o: k for k, o in enumerate(f25.gdf.orig)}
    pairs = [
        (to_kept24[a], to_kept25[b], iou)
        for a, b, iou in matches.itertuples(index=False)
        if a in to_kept24 and b in to_kept25
    ]
    ka = np.array([p[0] for p in pairs])
    kb = np.array([p[1] for p in pairs])
    g24, g25 = f24.gdf.iloc[ka].reset_index(drop=True), f25.gdf.iloc[kb].reset_index(drop=True)
    m24, m25 = f24.mean[ka, i24], f25.mean[kb, i25]
    d_raw = cosine_dist(m24, m25)
    c24 = f24.mean[:, i24].mean(axis=0)
    c25 = f25.mean[:, i25].mean(axis=0)
    d_cen = cosine_dist(m24 - c24, m25 - c25)
    hc_change = (g24.hcat_code.values != g25.hcat_code.values).astype(int)
    rg_change = (g24.season_regime.values != g25.season_regime.values).astype(int)
    grp = np.where(
        rg_change == 1,
        "regime_changed",
        np.where(hc_change == 1, "hcat_changed_same_regime", "hcat_same"),
    )
    area = g25.area_m2.values
    out: dict[str, Any] = {
        "n_matched_total": int(len(matches)),
        "n_matched_kept": len(pairs),
        "n_hcat_changed": int(hc_change.sum()),
        "n_regime_changed": int(rg_change.sum()),
    }
    print(
        f"\n  matched parcels (IoU>{IOU_MATCH}, mutual best): {len(matches)} total, "
        f"{len(pairs)} with >= {MIN_PIXELS} px in both years"
    )
    print(f"  hcat changed: {hc_change.sum()}  | season_regime changed: {rg_change.sum()}")
    for dname, d in (("raw", d_raw), ("centred", d_cen)):
        res: dict[str, Any] = {}
        for lname, lab in (("hcat_change", hc_change), ("regime_change", rg_change)):
            if lab.min() == lab.max():
                continue
            auc, lo, hi = auc_with_ci(lab, d)
            res[lname] = {"auc": auc, "ci95": [lo, hi]}
            big = area >= 10000
            if len(set(lab[big])) == 2:
                res[lname]["auc_ge_1ha"] = float(roc_auc_score(lab[big], d[big]))
                res[lname]["n_ge_1ha"] = int(big.sum())
        same_reg = rg_change == 0
        if len(set(hc_change[same_reg])) == 2:
            res["hcat_change_auc_within_same_regime"] = {
                "auc": float(roc_auc_score(hc_change[same_reg], d[same_reg])),
                "n": int(same_reg.sum()),
                "n_changed": int(hc_change[same_reg].sum()),
            }
        res["median_dist"] = {str(g): float(np.median(d[grp == g])) for g in np.unique(grp)}
        res["n_group"] = {str(g): int(np.sum(grp == g)) for g in np.unique(grp)}
        res["median_dist_hcat_same_vs_changed"] = {
            "same": float(np.median(d[hc_change == 0])),
            "changed": float(np.median(d[hc_change == 1])),
        }
        out[dname] = res
        print(f"  cosine distance ({dname} means):")
        for lname in ("hcat_change", "regime_change"):
            if lname in res:
                r = res[lname]
                extra = (
                    f", AUC>=1ha {r['auc_ge_1ha']:.3f} (n={r['n_ge_1ha']})"
                    if "auc_ge_1ha" in r
                    else ""
                )
                print(
                    f"    AUC {lname}: {r['auc']:.3f} [95% CI {r['ci95'][0]:.3f}, {r['ci95'][1]:.3f}]{extra}"
                )
        if "hcat_change_auc_within_same_regime" in res:
            print(f"    {res['hcat_change_auc_within_same_regime']} (same-regime pairs only)")
        print(f"    median distance by group: {res['median_dist']}  n={res['n_group']}")
    # Which hcat->hcat transitions are the "misses"
    trans = pd.DataFrame({"from": g24.hcat_name, "to": g25.hcat_name, "d": d_raw, "reg": grp})
    top = (
        trans[trans["from"] != trans["to"]]
        .groupby(["from", "to"])
        .d.agg(["count", "median"])
        .sort_values("count", ascending=False)
        .head(8)
    )
    print("  most common hcat transitions (raw cosine distance):")
    print("    " + top.round(4).to_string().replace("\n", "\n    "))
    out["top_transitions"] = {
        f"{a}->{b}": [int(r["count"]), float(r["median"])] for (a, b), r in top.iterrows()
    }

    # Multi-year: YoY cosine distance on the 2025 geometry for example parcels
    series_all = np.stack(
        [cosine_dist(f25.mean[kb, k], f25.mean[kb, k + 1]) for k in range(len(grid.years) - 1)],
        axis=1,
    )
    yy = [f"{grid.years[k]}->{grid.years[k + 1]}" for k in range(len(grid.years) - 1)]
    out["yoy_median_all_matched"] = {
        y: float(np.median(series_all[:, k])) for k, y in enumerate(yy)
    }
    print(
        "\n  YoY cosine distance on matched parcels (2025 geometry), median over parcels: "
        + ", ".join(f"{y} {v:.3f}" for y, v in out["yoy_median_all_matched"].items())
    )
    examples = {}
    picks = {
        "same hcat, winter_cereal": (grp == "hcat_same")
        & (g25.season_regime.values == "winter_cereal"),
        "same hcat, summer_crop": (grp == "hcat_same")
        & (g25.season_regime.values == "summer_crop"),
        "regime changed": grp == "regime_changed",
    }
    for label, cond in picks.items():
        cand = np.where(cond & (f25.n_px[kb] >= 30))[0]
        if cand.size == 0:  # tiny group (e.g. same-crop summer crops): accept smaller parcels
            cand = np.where(cond)[0]
        if cand.size == 0:
            continue
        j = cand[np.argmax(area[cand])]  # largest parcel in the group: no cherry-picking
        series = series_all[j]
        examples[label] = {
            "field_id_2025": str(g25.field_id[j]),
            "hcat_2024": g24.hcat_name[j],
            "hcat_2025": g25.hcat_name[j],
            "area_ha": float(area[j] / 1e4),
            "n_px": int(f25.n_px[kb[j]]),
            "yoy": dict(zip(yy, [float(v) for v in series], strict=True)),
        }
        print(
            f"    [{label}] {g24.hcat_name[j]} (2024) -> {g25.hcat_name[j]} (2025), "
            f"{area[j] / 1e4:.1f} ha, {f25.n_px[kb[j]]} px: "
            + "  ".join(f"{y} {v:.3f}" for y, v in zip(yy, series, strict=True))
        )
    out["examples"] = examples
    out["_arrays"] = {"d_raw": d_raw, "grp": grp, "hc_change": hc_change}
    return out


# --------------------------------------------------------------------------------------------
# Step 5: FTW block splitting
# --------------------------------------------------------------------------------------------


def ftw_splitting(fs25: FieldSet, grid: Grid, ftw_path: Path) -> dict[str, Any]:
    ftw = gpd.read_parquet(ftw_path).to_crs(grid.crs).reset_index(drop=True)
    ftw_geoms = ftw.geometry.values
    tree = STRtree(ftw_geoms)
    assign = np.full(len(fs25.gdf), -1)
    for j, g in enumerate(fs25.gdf.geometry.values):
        cand = tree.query(g, predicate="intersects")
        if cand.size == 0:
            continue
        areas = shapely.area(shapely.intersection(g, ftw_geoms[cand]))
        if areas.max() >= 0.5 * g.area:
            assign[j] = cand[int(np.argmax(areas))]
    counts = pd.Series(assign[assign >= 0]).value_counts()
    multi = counts[counts >= 2].index.to_numpy()
    print(
        f"\n  FTW 2025 polygons: {len(ftw)} in AOI; declared parcels assigned to a polygon: "
        f"{int((assign >= 0).sum())}/{len(assign)}; polygons with >=1 parcel: {len(counts)}, "
        f">=2 parcels: {len(multi)} (parcels per polygon, max {int(counts.max())})"
    )

    owner = np.full(grid.height * grid.width, -1, dtype=np.int32)
    for j, p in enumerate(fs25.pix):
        owner[p] = j
    # sensitivity: truth that also includes the mixed boundary pixels of the declared parcels
    owner_edge = np.full(grid.height * grid.width, -1, dtype=np.int32)
    for j, g in enumerate(fs25.gdf.geometry.values):
        owner_edge[pixel_indices(g, grid)] = j
    flat = grid.flat(2025)
    finite = finite_pixels(grid)
    rows = []
    skipped = 0
    for fid in multi:
        geom = ftw_geoms[fid]
        idx, _ = interior_pixels(geom, grid)
        if idx.size < FTW_MIN_PIXELS:
            idx = pixel_indices(geom, grid)
        idx = idx[finite[idx]]  # NaN gaps between parcels cannot be clustered
        members = np.where(assign == fid)[0]
        truth = np.where(np.isin(owner[idx], members), owner[idx], -1)
        lab = truth >= 0
        if idx.size < FTW_MIN_PIXELS or lab.sum() < 20 or len(set(truth[lab])) < 2:
            skipped += 1
            continue
        x = flat[idx].astype(np.float32)
        xy = np.stack([idx % grid.width, idx // grid.width], axis=1).astype(np.float32) * 10.0
        sil, fits = {}, {}
        for k in FTW_K_RANGE:
            if idx.size <= k + 1:
                continue
            lbl = KMeans(k, n_init=5, random_state=SEED).fit_predict(x)
            if len(set(lbl)) < 2:
                continue
            fits[k] = lbl
            sil[k] = silhouette_score(
                x, lbl, sample_size=min(idx.size, SILHOUETTE_SAMPLE), random_state=SEED
            )
        if not sil:
            skipped += 1
            continue
        k = max(sil, key=lambda kk: sil[kk])
        n_true = len(set(truth[lab]))
        ari_emb = adjusted_rand_score(truth[lab], fits[k][lab])
        sp = KMeans(k, n_init=5, random_state=SEED).fit_predict(xy)
        ari_sp = adjusted_rand_score(truth[lab], sp[lab])
        truth_e = np.where(np.isin(owner_edge[idx], members), owner_edge[idx], -1)
        lab_e = truth_e >= 0
        ari_emb_e = adjusted_rand_score(truth_e[lab_e], fits[k][lab_e])
        ari_sp_e = adjusted_rand_score(truth_e[lab_e], sp[lab_e])
        k_or = min(n_true, 8)
        ari_emb_or = adjusted_rand_score(
            truth[lab], KMeans(k_or, n_init=5, random_state=SEED).fit_predict(x)[lab]
        )
        ari_sp_or = adjusted_rand_score(
            truth[lab], KMeans(k_or, n_init=5, random_state=SEED).fit_predict(xy)[lab]
        )
        n_hcat = fs25.gdf.hcat_code.iloc[members].nunique()
        n_regime = fs25.gdf.season_regime.iloc[members].nunique()
        rows.append(
            {
                "ftw_idx": int(fid),
                "n_px": int(idx.size),
                "n_true": n_true,
                "k": int(k),
                "sil": float(sil[k]),
                "n_hcat": int(n_hcat),
                "n_regime": int(n_regime),
                "ari_emb": ari_emb,
                "ari_sp": ari_sp,
                "ari_emb_edge": ari_emb_e,
                "ari_sp_edge": ari_sp_e,
                "ari_emb_oracle": ari_emb_or,
                "ari_sp_oracle": ari_sp_or,
            }
        )
    df = pd.DataFrame(rows)
    out: dict[str, Any] = {
        "n_ftw_polygons": int(len(ftw)),
        "n_multi_parcel": int(len(multi)),
        "n_evaluated": int(len(df)),
        "n_skipped": skipped,
    }
    if df.empty:
        return out
    d = df.ari_emb - df.ari_sp
    do = df.ari_emb_oracle - df.ari_sp_oracle
    out.update(
        {
            "median_ari_emb": float(df.ari_emb.median()),
            "median_ari_spatial": float(df.ari_sp.median()),
            "emb_beats_spatial": float((d > 1e-9).mean()),
            "tie": float((d.abs() <= 1e-9).mean()),
            "median_ari_emb_oracle_k": float(df.ari_emb_oracle.median()),
            "median_ari_spatial_oracle_k": float(df.ari_sp_oracle.median()),
            "emb_beats_spatial_oracle_k": float((do > 1e-9).mean()),
            "k_equals_n_true": float((df.k == df.n_true).mean()),
            "k_within_1_of_n_true": float(((df.k - df.n_true).abs() <= 1).mean()),
            "k_equals_min(n_true,4)": float((df.k == df.n_true.clip(upper=4)).mean()),
            "median_k": float(df.k.median()),
            "median_n_true": float(df.n_true.median()),
            "k_hist": {int(k): int(v) for k, v in df.k.value_counts().sort_index().items()},
            "n_true_hist": {
                int(k): int(v) for k, v in df.n_true.value_counts().sort_index().items()
            },
        }
    )
    try:
        out["wilcoxon_p_emb_vs_spatial"] = float(stats.wilcoxon(df.ari_emb, df.ari_sp).pvalue)
    except ValueError:
        out["wilcoxon_p_emb_vs_spatial"] = None
    diff_crop = df.n_hcat >= 2
    out["by_n_true"] = {}
    for name, mask in (
        ("2", df.n_true == 2),
        ("3-4", df.n_true.between(3, 4)),
        (">=5", df.n_true >= 5),
    ):
        if mask.any():
            out["by_n_true"][name] = {
                "n": int(mask.sum()),
                "median_ari_emb": float(df.ari_emb[mask].median()),
                "median_ari_spatial": float(df.ari_sp[mask].median()),
                "median_ari_emb_oracle_k": float(df.ari_emb_oracle[mask].median()),
                "k_equals_min(n_true,4)": float(
                    (df.k[mask] == df.n_true[mask].clip(upper=4)).mean()
                ),
            }
    out["with_boundary_pixels_in_truth"] = {
        "n_labelled_px_ratio_note": "truth includes mixed edge pixels of declared parcels",
        "median_ari_emb": float(df.ari_emb_edge.median()),
        "median_ari_spatial": float(df.ari_sp_edge.median()),
        "emb_beats_spatial": float((df.ari_emb_edge - df.ari_sp_edge > 1e-9).mean()),
    }
    out["share_ari_emb_ge_0.5"] = float((df.ari_emb >= 0.5).mean())
    out["median_silhouette_chosen_k"] = float(df.sil.median())
    out["by_crop_diversity"] = {}
    for name, mask in (
        ("all_parcels_same_hcat", ~diff_crop),
        ("parcels_differ_in_hcat", diff_crop),
    ):
        if mask.any():
            out["by_crop_diversity"][name] = {
                "n": int(mask.sum()),
                "median_ari_emb": float(df.ari_emb[mask].median()),
                "median_ari_spatial": float(df.ari_sp[mask].median()),
                "emb_beats_spatial": float((d[mask] > 1e-9).mean()),
                "median_ari_emb_oracle_k": float(df.ari_emb_oracle[mask].median()),
                "median_ari_spatial_oracle_k": float(df.ari_sp_oracle[mask].median()),
            }
    print(f"  evaluated {len(df)} polygons (skipped {skipped}: too few labelled px / one parcel)")
    print(
        f"  chosen k vs declared parcels: median k {out['median_k']:.0f}, median n_true "
        f"{out['median_n_true']:.0f}; k==n_true {out['k_equals_n_true']:.2f}, "
        f"|k-n_true|<=1 {out['k_within_1_of_n_true']:.2f}, k==min(n_true,4) "
        f"{out['k_equals_min(n_true,4)']:.2f}; k hist {out['k_hist']}; n_true hist {out['n_true_hist']}"
    )
    print(
        f"  ARI (chosen k): embeddings median {out['median_ari_emb']:.3f} vs spatial "
        f"{out['median_ari_spatial']:.3f}; emb wins {out['emb_beats_spatial']:.2f}, ties "
        f"{out['tie']:.2f}; Wilcoxon p={out['wilcoxon_p_emb_vs_spatial']}"
    )
    print(
        f"  ARI (oracle k=n_true): embeddings {out['median_ari_emb_oracle_k']:.3f} vs spatial "
        f"{out['median_ari_spatial_oracle_k']:.3f}; emb wins {out['emb_beats_spatial_oracle_k']:.2f}"
    )
    for name, r in out["by_crop_diversity"].items():
        print(f"    {name}: {r}")
    for name, r in out["by_n_true"].items():
        print(f"    n_true {name}: {r}")
    print(f"  sensitivity, truth incl. boundary pixels: {out['with_boundary_pixels_in_truth']}")
    print(
        f"  share of polygons with embedding ARI >= 0.5: {out['share_ari_emb_ge_0.5']:.2f}; "
        f"median silhouette at chosen k: {out['median_silhouette_chosen_k']:.2f}"
    )
    out["_df"] = df
    return out


# --------------------------------------------------------------------------------------------
# Step 6: archetypes
# --------------------------------------------------------------------------------------------


def purity(labels: np.ndarray, truth: np.ndarray) -> float:
    ct = pd.crosstab(labels, truth)
    return float(ct.max(axis=1).sum() / ct.values.sum())


def archetypes(fs25: FieldSet, grid: Grid) -> dict[str, Any]:
    feats = fs25.mean[:, grid.years.index(2025)]
    out: dict[str, Any] = {}
    reg = fs25.gdf.season_regime.values.astype(str)
    hc = fs25.gdf.hcat_name.values.astype(str)
    out["majority_purity_regime"] = float(pd.Series(reg).value_counts(normalize=True).iloc[0])
    for vname, x in (("raw", feats), ("standardised", StandardScaler().fit_transform(feats))):
        lbl = KMeans(ARCHETYPE_K, n_init=20, random_state=SEED).fit_predict(x)
        res = {
            "purity_regime": purity(lbl, reg),
            "nmi_regime": float(normalized_mutual_info_score(reg, lbl)),
            "ari_regime": float(adjusted_rand_score(reg, lbl)),
            "purity_hcat": purity(lbl, hc),
            "nmi_hcat": float(normalized_mutual_info_score(hc, lbl)),
            "contingency_regime": pd.crosstab(
                pd.Series(lbl, name="cluster"), pd.Series(reg, name="regime")
            ).to_dict("index"),
        }
        out[vname] = res
        print(
            f"\n  k-means k={ARCHETYPE_K} on 2025 field means ({vname}): regime purity "
            f"{res['purity_regime']:.3f} (majority-class baseline {out['majority_purity_regime']:.3f}), "
            f"NMI {res['nmi_regime']:.3f}, ARI {res['ari_regime']:.3f}; HCAT purity "
            f"{res['purity_hcat']:.3f}, NMI {res['nmi_hcat']:.3f}"
        )
        print(
            "    "
            + pd.crosstab(pd.Series(lbl, name="cluster"), pd.Series(reg, name="regime"))
            .to_string()
            .replace("\n", "\n    ")
        )
    return out


# --------------------------------------------------------------------------------------------
# Step 7: outputs
# --------------------------------------------------------------------------------------------


def write_parquet(fs: FieldSet, grid: Grid, path: Path) -> None:
    yi = grid.years.index(fs.year)
    g = fs.gdf
    cols = [
        "field_id",
        "crop_code",
        "crop_name",
        "hcat_code",
        "hcat_name",
        "season_regime",
        "area_m2",
        "year",
    ]
    table = pa.Table.from_pandas(g[cols].reset_index(drop=True), preserve_index=False)
    table = table.append_column("pixel_count", pa.array(fs.n_px, type=pa.int32()))
    table = table.append_column("buffer_applied", pa.array(fs.buffered))
    table = table.append_column("grid_coverage", pa.array(fs.coverage, type=pa.float32()))
    vec = pa.list_(pa.float32())
    table = table.append_column("embedding_mean", pa.array(fs.mean[:, yi].tolist(), type=vec))
    table = table.append_column("embedding_std", pa.array(fs.std[:, yi].tolist(), type=vec))
    pq.write_table(table, path)


def make_plots(
    fs25: FieldSet, grid: Grid, rot: dict[str, Any], ftw: dict[str, Any], out_dir: Path
) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    written = []
    feats = fs25.mean[:, grid.years.index(2025)]
    pca = PCA(2).fit(feats)
    z = pca.transform(feats)
    fig, ax = plt.subplots(figsize=(7, 5.5))
    for reg, colour in REGIME_COLOURS.items():
        m = fs25.gdf.season_regime.values == reg
        if m.any():
            ax.scatter(
                z[m, 0],
                z[m, 1],
                s=8 + np.sqrt(fs25.gdf.area_m2.values[m]) / 4,
                c=colour,
                alpha=0.75,
                edgecolor="white",
                linewidth=0.4,
                label=f"{reg} ({m.sum()})",
            )
    ax.set_xlabel(f"PC1 ({pca.explained_variance_ratio_[0]:.0%})")
    ax.set_ylabel(f"PC2 ({pca.explained_variance_ratio_[1]:.0%})")
    ax.set_title("2025 field-mean TESSERA embeddings (PCA), by declared season regime")
    ax.legend(frameon=False, fontsize=8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    p = out_dir / "pca_field_means_2025.png"
    fig.savefig(p, dpi=140)
    plt.close(fig)
    written.append(p.name)

    arr = rot["_arrays"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    groups = ["hcat_same", "hcat_changed_same_regime", "regime_changed"]
    data = [arr["d_raw"][arr["grp"] == g] for g in groups]
    axes[0].boxplot(
        data,
        tick_labels=[
            f"{g.replace('_', ' ')}\n(n={len(d)})" for g, d in zip(groups, data, strict=True)
        ],
        showfliers=True,
    )
    axes[0].set_ylabel("cosine distance, field mean 2024 vs 2025")
    axes[0].set_title("Rotation: distance by declared change")
    if "_df" in ftw:
        df = ftw["_df"]
        axes[1].scatter(df.ari_sp, df.ari_emb, c="#0072B2", s=30, alpha=0.8)
        axes[1].plot([-0.2, 1], [-0.2, 1], color="#999999", linewidth=1)
        axes[1].set_xlabel("ARI, spatial k-means (same k)")
        axes[1].set_ylabel("ARI, embedding k-means")
        axes[1].set_title(f"FTW block splitting (n={len(df)} polygons)")
    for a in axes:
        for s in ("top", "right"):
            a.spines[s].set_visible(False)
    fig.tight_layout()
    p = out_dir / "rotation_and_ftw_2025.png"
    fig.savefig(p, dpi=140)
    plt.close(fig)
    written.append(p.name)
    return written


def strip_private(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): strip_private(v) for k, v in obj.items() if k not in ("_arrays", "_df")}
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    return obj


def main() -> None:
    ap = argparse.ArgumentParser(description="TESSERA field-level embedding signal spike")
    ap.add_argument("--embeddings", type=Path, default=Path("tessera_out/aoi_embeddings.npz"))
    ap.add_argument("--fields-dir", type=Path, default=Path("fields_out"))
    ap.add_argument("--out-dir", type=Path, default=Path("join_out"))
    ap.add_argument("--no-plots", action="store_true")
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    warnings.filterwarnings("ignore", category=UserWarning)
    results: dict[str, Any] = {}

    t_load = time.perf_counter()
    grid = load_grid(args.embeddings)
    print(f"loaded {args.embeddings.name} in {time.perf_counter() - t_load:.2f} s")
    print(f"grid: {grid.emb.shape} years {grid.years} crs {grid.crs}")

    print("\n== 1. field-level embedding artifact ==")
    t0 = time.perf_counter()
    fsets: dict[int, FieldSet] = {}
    for year in (2024, 2025):
        fsets[year] = build_field_set(
            load_declared(args.fields_dir / f"declared_{year}.parquet", grid.crs), grid, year
        )
    dt = time.perf_counter() - t0
    for year, fs in fsets.items():
        dr = fs.dropped
        print(
            f"  {year}: {len(fs.full)} parcels -> kept {len(fs.gdf)}, dropped {len(dr)} "
            f"(median area {dr.area_m2.median() if len(dr) else 0:.0f} m2, max "
            f"{dr.area_m2.max() if len(dr) else 0:.0f} m2); fallback-no-buffer used for "
            f"{int((~fs.buffered).sum())}; grid coverage < 90%: {int((fs.coverage < 0.9).sum())}; "
            f"pixels/field median {np.median(fs.n_px):.0f} (min {fs.n_px.min()}, "
            f"max {fs.n_px.max()})"
        )
    n_fields = sum(len(fs.gdf) for fs in fsets.values())
    print(
        f"  compute time: {dt:.2f} s for {n_fields} fields x {len(grid.years)} years "
        f"(mean+std, 128-d); {dt / n_fields * 1000:.1f} ms/field (embeddings already in memory)"
    )
    results["artifact"] = {
        "seconds": dt,
        "per_year": {
            str(y): {
                "parcels": len(fs.full),
                "kept": len(fs.gdf),
                "dropped": len(fs.dropped),
                "dropped_median_area_m2": float(fs.dropped.area_m2.median())
                if len(fs.dropped)
                else None,
                "dropped_max_area_m2": float(fs.dropped.area_m2.max()) if len(fs.dropped) else None,
                "fallback_no_buffer": int((~fs.buffered).sum()),
                "grid_coverage_lt_90pct": int((fs.coverage < 0.9).sum()),
                "median_pixels": float(np.median(fs.n_px)),
            }
            for y, fs in fsets.items()
        },
    }

    tasks = label_tasks(fsets)
    print(
        "\n== 2a. field-level CV (stratified 5-fold x "
        f"{N_REPEATS} repeats; fields are units; mean±sd over repeats) =="
    )
    results["field_cv"] = separability(fsets, grid, tasks)
    print("\n== 2b. pixel-level CV, folds grouped by field ==")
    results["pixel_cv"] = pixel_level_cv(fsets, grid, tasks)

    print("\n== 3/4. matching 2024 <-> 2025 parcels ==")
    matches = match_editions(fsets[2024].full, fsets[2025].full, IOU_MATCH)
    print("\n== 3. temporal transfer ==")
    results["transfer"] = temporal_transfer(fsets, grid, tasks, matches, results["field_cv"])
    print("\n== 4. rotation detection ==")
    rot = rotation(fsets, grid, matches)
    results["rotation"] = rot

    print("\n== 5. FTW block splitting (2025) ==")
    ftw = ftw_splitting(fsets[2025], grid, args.fields_dir / "ftw_2025.parquet")
    results["ftw_split"] = ftw

    print("\n== 6. unsupervised archetypes ==")
    results["archetypes"] = archetypes(fsets[2025], grid)

    print("\n== 7. outputs ==")
    for year, fs in fsets.items():
        p = args.out_dir / f"field_embeddings_{year}.parquet"
        write_parquet(fs, grid, p)
        print(f"  wrote {p} ({p.stat().st_size / 1e6:.2f} MB, {len(fs.gdf)} rows)")
    if not args.no_plots:
        for name in make_plots(fsets[2025], grid, rot, ftw, args.out_dir):
            print(f"  wrote {args.out_dir / name}")
    jp = args.out_dir / "results.json"
    jp.write_text(json.dumps(strip_private(results), indent=2, default=str))
    print(f"  wrote {jp}")


if __name__ == "__main__":
    main()
