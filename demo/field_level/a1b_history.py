"""A1b: 11-year crop history (2015-2025; BB 2015-2023) and a temporal hold-out of the embedding
signals on years never used for calibration (2018, and 2017 where TESSERA has data).

- rotation: centred YoY cosine distance >= 0.5 vs declared change, for the pairs 2017->18 and 2018->19
- crop group: logistic model trained on 2019+ unit-years only, applied to 2018 (and 2017)
- how much a 7-year window under-states monoculture runs / cereal share vs the full history"""

import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, os.path.dirname(__file__))
from common import ARABLE, CEREAL, group  # noqa: E402

name, D = sys.argv[1], sys.argv[2]
U = json.load(open(f"{D}/{name}/units.json"))
H = json.load(open(f"{D}/{name}/units_history.json"))
T = np.load(f"{D}/{name}/tessera_units.npz")
TH = np.load(f"{D}/{name}/tessera_units_hist.npz")
F = pd.read_csv(f"{D}/{name}/features.csv")
uids = [u["uid"] for u in U["units"]]
# per-unit label for every year
lab = {}
for k, u in enumerate(U["units"]):
    for y, d in H[u["uid"]].items():
        lab[(k, int(y))] = d
    for y, d in u["years"].items():
        lab[(k, int(y))] = d
years_all = sorted({y for _, y in lab})
# centred embeddings per year
E = {int(y): T["means"][i] - T["aoi"][i] for i, y in enumerate(T["years"])}
for i, y in enumerate(TH["years"]):
    if (TH["counts"][i] >= 5).sum() > 0:
        E[int(y)] = TH["means"][i] - TH["aoi"][i]
R = dict(history_years=[int(y) for y in years_all], tessera_hist_years=[int(y) for y in TH["years"] if (TH["counts"][list(TH["years"]).index(y)] >= 5).sum() > 0])


def cos(a, b):
    return 1 - a @ b / (np.linalg.norm(a) * np.linalg.norm(b))


# rotation hold-out pairs
for y0 in (2017, 2018):
    y1 = y0 + 1
    if y0 not in E or y1 not in E:
        continue
    rows = []
    for k in range(len(uids)):
        a, b = lab.get((k, y0)), lab.get((k, y1))
        e0, e1 = E[y0][k], E[y1][k]
        if a and b and np.isfinite(e0).all() and np.isfinite(e1).all():
            rows.append((a["hcat"] != b["hcat"], cos(e0, e1)))
    y, s = np.array([r[0] for r in rows]), np.array([r[1] for r in rows])
    f = s >= 0.5
    R[f"rotation_holdout_{y0}_{y1}"] = dict(n=len(y), changed=round(float(y.mean()), 3), auc=round(float(roc_auc_score(y, s)), 3),
                                             precision=round(float((f & y).sum() / f.sum()), 3), recall=round(float((f & y).sum() / y.sum()), 3))
# crop-group hold-out: train on 2019+ only
tr = F[F.tracked & F.group.notna() & (F.tess_px >= 5)]
Xtr = np.stack([E[int(y)][int(i)] for y, i in zip(tr.year, tr.ui)])
clf = make_pipeline(StandardScaler(), LogisticRegression(max_iter=3000, C=0.5)).fit(Xtr, tr.group)
for y in (2017, 2018):
    if y not in E:
        continue
    k = [k for k in range(len(uids)) if lab.get((k, y)) and np.isfinite(E[y][k]).all()]
    g = np.array([group(lab[(i, y)]["hcat_code"], lab[(i, y)]["hcat"]) for i in k])
    m = np.isin(g, clf.classes_)
    pred = clf.predict(E[y][np.array(k)][m])
    R[f"group_holdout_{y}"] = dict(n=int(m.sum()), acc=round(float((pred == g[m]).mean()), 3), majority=round(float(pd.Series(g[m]).value_counts(normalize=True).iloc[0]), 3))
# full-history rotation profiles vs the 2019+ window
prof = []
for k, uid in enumerate(uids):
    def stats(ys):
        seq = [lab.get((k, y)) for y in ys]
        grp = [group(d["hcat_code"], d["hcat"]) if d else None for d in seq]
        dec = [g for g in grp if g]
        if len(dec) < 0.6 * len(ys) or sum(g in ARABLE for g in dec) < 0.8 * len(dec):
            return None
        run = best = 1
        for a, b in zip(seq, seq[1:]):
            run = run + 1 if (a and b and a["hcat"] == b["hcat"]) else 1
            best = max(best, run)
        return dict(cereal=sum(g in CEREAL for g in dec) / len(dec), run=best, ncrops=len({d["hcat"] for d in seq if d}))
    full, recent = stats(years_all), stats([y for y in years_all if y >= 2019])
    if full and recent:
        prof.append(dict(uid=uid, cereal_full=full["cereal"], cereal_recent=recent["cereal"], run_full=full["run"], run_recent=recent["run"], n_full=full["ncrops"], n_recent=recent["ncrops"]))
P = pd.DataFrame(prof)
P.to_csv(f"{D}/{name}/rotation_profiles_full.csv", index=False)
R["profiles_full_vs_recent"] = dict(n_units=len(P), years_full=len(years_all), monoculture_run_ge3_full=round(float((P.run_full >= 3).mean()), 3), monoculture_run_ge3_recent=round(float((P.run_recent >= 3).mean()), 3),
                                    run_longer_in_full=round(float((P.run_full > P.run_recent).mean()), 3), cereal_share_abs_diff_median=round(float((P.cereal_full - P.cereal_recent).abs().median()), 3),
                                    cereal_ge_0_6_full=round(float((P.cereal_full >= 0.6).mean()), 3), cereal_ge_0_6_recent=round(float((P.cereal_recent >= 0.6).mean()), 3),
                                    n_crops_median_full=float(P.n_full.median()), n_crops_median_recent=float(P.n_recent.median()))
json.dump(R, open(f"results/{name}_a1b_history.json", "w"), indent=1)
print(json.dumps(R, indent=1))
