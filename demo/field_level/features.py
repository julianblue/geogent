"""One row per (unit, year): declaration, TESSERA, S2 phenology, peer percentiles.

usage: python features.py <window> <datadir> -> <datadir>/<window>/features.csv
Peers = same declared HCAT class, same year, centroid within 5 km, >=5 peers.
z_peer = (x - peer median) / peer MAD-sigma, i.e. the season and crop effect removed."""

import json
import os
import sys

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from shapely import wkt
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, os.path.dirname(__file__))
from common import group  # noqa: E402

name, D = sys.argv[1], sys.argv[2]
U = json.load(open(f"{D}/{name}/units.json"))
PH = json.load(open(f"{D}/{name}/pheno.json"))
CY = json.load(open(f"{D}/{name}/cycles.json")) if os.path.exists(f"{D}/{name}/cycles.json") else {}
CROP_AWARE = ("peak_ndvi", "peak_doy", "sos", "eos", "harvest_doy", "indvi_season")
T = np.load(f"{D}/{name}/tessera_units.npz")
years = U["years"]
units = U["units"]
cent = np.array([wkt.loads(u["wkt"]).centroid.coords[0] for u in units])
E = T["means"] - T["aoi"][:, None, :]  # year-centred
rows = []
for yi, y in enumerate(years):
    for i, u in enumerate(units):
        d = u["years"][str(y)]
        ph = PH.get(str(y), [None] * len(units))[i]
        r = dict(uid=u["uid"], year=y, ha=round(u["ha"], 2), x=cent[i, 0], y_=cent[i, 1], tracked=d is not None,
                 crop=d["crop"] if d else None, hcat=d["hcat"] if d else None, hcat_code=d["hcat_code"] if d else None,
                 group=group(d["hcat_code"], d["hcat"]) if d else None, tess_px=int(T["counts"][yi, i]), tess_disp=float(T["disp"][yi, i]))
        if yi > 0 and T["counts"][yi, i] >= 5 and T["counts"][yi - 1, i] >= 5:
            a, b = E[yi, i], E[yi - 1, i]
            r["emb_yoy_centred"] = float(1 - a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))
        if ph:
            r.update({k: v for k, v in ph.items() if k not in ("ndvi_smooth", "cycle_peaks")})
            # crop-aware main-cycle metrics (cycles_ts.py) replace the naive year-max ones; naive kept as *_naive
            cy = CY.get(str(y), [None] * len(units))[i]
            if cy is not None:
                for k in CROP_AWARE:
                    r[f"{k}_naive"] = r.get(k)
                r["main_cycle_found"] = cy["main_found"] or cy.get("main_kind") == "weak"
                r["n_cover_cycles"] = cy["n_cover_cycles"]
                if "peak_ndvi" in cy:
                    r.update({k: cy[k] for k in CROP_AWARE})
                    r["season_len"] = cy["eos"] - cy["sos"]
                    r["pre_cover"] = cy["pre_cover"]
        rows.append(r)
F = pd.DataFrame(rows)
F["ui"] = np.tile(np.arange(len(units)), len(years))
prev = F.set_index(["uid", "year"])["hcat"]
F["prev_hcat"] = [prev.get((u, y - 1)) for u, y in zip(F.uid, F.year)]
F["declared_change"] = np.where(F.hcat.notna() & F.prev_hcat.notna(), F.hcat != F.prev_hcat, np.nan)

# leave-one-year-out crop-group model on centred unit embeddings -> P(declared group), predicted group
ok = F.tracked & (F.tess_px >= 5) & F.group.notna()
X = E.reshape(-1, E.shape[-1])
F["p_declared_group"] = np.nan
F["emb_group"] = None
for y in years:
    tr, te = ok & (F.year != y), (F.year == y) & (F.tess_px >= 5)
    clf = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=0.5)).fit(X[tr.values], F.group[tr])
    pr = clf.predict_proba(X[te.values])
    cls = list(clf.classes_)
    F.loc[te, "emb_group"] = np.array(cls)[pr.argmax(1)]
    pd_ = [pr[k, cls.index(g)] if g in cls else np.nan for k, g in enumerate(F.group[te])]
    F.loc[te, "p_declared_group"] = pd_

# peer percentiles
for col in ("indvi_season", "indvi_year", "peak_ndvi", "peak_doy", "harvest_doy"):
    F[f"{col}_pct"] = np.nan
    F[f"{col}_zpeer"] = np.nan
F["n_peers"] = 0
for (y, h), g in F[F.tracked & F.peak_ndvi.notna()].groupby(["year", "hcat"]):
    if len(g) < 6:
        continue
    xy = g[["x", "y_"]].values
    tree = cKDTree(xy)
    for idx, nb in zip(g.index, tree.query_ball_point(xy, 5000)):
        nb = [g.index[k] for k in nb if g.index[k] != idx]
        if len(nb) < 5:
            continue
        F.at[idx, "n_peers"] = len(nb)
        for col in ("indvi_season", "indvi_year", "peak_ndvi", "peak_doy", "harvest_doy"):
            v = F.loc[nb, col].dropna().values
            x0 = F.at[idx, col]
            if len(v) < 5 or pd.isna(x0):
                continue
            F.at[idx, f"{col}_pct"] = (np.sum(v < x0) + 0.5 * np.sum(v == x0)) / len(v)
            mad = 1.4826 * np.median(np.abs(v - np.median(v))) or np.std(v) or 1
            F.at[idx, f"{col}_zpeer"] = (x0 - np.median(v)) / mad
F.to_csv(f"{D}/{name}/features.csv", index=False)
print(name, F.shape, "tracked+pheno", int((F.tracked & F.peak_ndvi.notna()).sum()), "with peers", int((F.n_peers >= 5).sum()))
