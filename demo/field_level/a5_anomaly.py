"""A5 anomaly / event screening per unit-year.

Scores (robust z within declared HCAT class x year, >=8 members):
- traj_dev: RMSE of the unit's smoothed NDVI curve to the class-year median curve
- emb_dev: distance of the centred TESSERA mean to the class-year centroid (self excluded)
Rule-based event candidates: low peak (peak NDVI z_peer <= -3; failure or severe underperformance candidate), delayed / resown
(peak >= 25 d after peers and z >= 3), no harvest signal (declared arable, no >=0.3 drop).
Validation: (1) declared '... WITHOUT HARVEST' classes vs their with-harvest counterpart;
(2) blinded manual review of curves (panels + key written to <datadir>, key opened after labels)."""

import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

sys.path.insert(0, os.path.dirname(__file__))
from common import ARABLE, GRID  # noqa: E402

name, D = sys.argv[1], sys.argv[2]
F = pd.read_csv(f"{D}/{name}/features.csv")
PH = json.load(open(f"{D}/{name}/pheno.json"))
T = np.load(f"{D}/{name}/tessera_units.npz")
yrs = list(T["years"])
E = T["means"] - T["aoi"][:, None, :]
F["traj_dev"] = np.nan
F["emb_dev"] = np.nan
F["traj_dev_season"] = np.nan
curves = {}
for (y, h), g in F[F.tracked & F.peak_ndvi.notna()].groupby(["year", "hcat"]):
    if len(g) < 8:
        continue
    C = np.array([PH[str(y)][i]["ndvi_smooth"] for i in g.ui])
    med = np.median(C, 0)
    curves[(y, h)] = (np.percentile(C, 10, 0), med, np.percentile(C, 90, 0))
    rm = np.sqrt(((C - med) ** 2).mean(1))
    # in-season only: between the class-year p10 start and p90 end of season
    win = (GRID >= g.sos.quantile(.1)) & (GRID <= g.eos.quantile(.9))
    rs = np.sqrt(((C[:, win] - med[win]) ** 2).mean(1))
    X = E[yrs.index(y), g.ui.values]
    ok = np.isfinite(X).all(1)
    s = X[ok].sum(0)
    dd = np.full(len(g), np.nan)
    dd[ok] = np.linalg.norm(X[ok] - (s - X[ok]) / (ok.sum() - 1), axis=1)
    for col, v in (("traj_dev", rm), ("traj_dev_season", rs), ("emb_dev", dd)):
        mu, mad = np.nanmedian(v), 1.4826 * np.nanmedian(np.abs(v - np.nanmedian(v)))
        F.loc[g.index, col] = (v - mu) / max(mad, 1e-6)
F["anomaly"] = F[["traj_dev", "emb_dev"]].max(axis=1)
ar = F.group.isin(ARABLE) & F.tracked
F["ev_low_peak"] = ar & (F.peak_ndvi_zpeer <= -3)
F["ev_delayed_resown"] = ar & (F.peak_doy_zpeer >= 3) & ((F.peak_doy - (F.peak_doy - 0)).notna())
pk = F.groupby(["year", "hcat"]).peak_doy.transform("median")
F["ev_delayed_resown"] = ar & (F.peak_doy_zpeer >= 3) & (F.peak_doy - pk >= 25)
# no main-crop cycle inside the declared crop's window (cycles_ts.py), else no harvest drop after it
F["ev_no_harvest"] = ar & F.peak_ndvi.notna() & ((F.main_cycle_found == False) | F.harvest_doy.isna()) if "main_cycle_found" in F else ar & F.peak_ndvi.notna() & F.harvest_doy.isna()  # noqa: E712
F.to_csv(f"{D}/{name}/anomaly.csv", index=False)
R = dict(n_scored=int(F.anomaly.notna().sum()), top2pct_threshold=round(float(F.anomaly.quantile(.98)), 2),
         spearman_traj_vs_emb=round(F[["traj_dev", "emb_dev"]].corr("spearman").iloc[0, 1], 3),
         event_counts={k: int(F[k].sum()) for k in ("ev_low_peak", "ev_delayed_resown", "ev_no_harvest")},
         event_rate_arable={k: round(F.loc[ar, k].mean(), 4) for k in ("ev_low_peak", "ev_delayed_resown", "ev_no_harvest")})
# validation 1: declared without-harvest classes (scored against the pooled with-harvest class-year)
wh = F[F.hcat.str.contains("WITHOUT HARVEST", na=False) & F.peak_ndvi.notna()]
if len(wh) >= 10:
    base = F[F.hcat.str.contains("FIELD VEGETABLES SINGLE CULTURE", na=False) & F.peak_ndvi.notna()]
    both = pd.concat([wh.assign(t=1), base.assign(t=0)])
    # score both against the with-harvest class-year curve (the class a reviewer would expect)
    dev = []
    for _, r in both.iterrows():
        c = curves.get((r.year, "FIELD VEGETABLES SINGLE CULTURE"))
        dev.append(np.nan if c is None else np.sqrt(((np.array(PH[str(r.year)][r.ui]["ndvi_smooth"]) - c[1]) ** 2).mean()))
    both["dev_vs_harvested"] = dev
    ok = both.dev_vs_harvested.notna()
    R["validation_without_harvest"] = dict(n_without=int(both.t[ok].sum()), n_with=int((1 - both.t[ok]).sum()),
                                           auc_traj_dev=round(roc_auc_score(both.t[ok], both.dev_vs_harvested[ok]), 3),
                                           auc_no_harvest_rule=round(roc_auc_score(both.t[ok], both.harvest_doy[ok].isna()), 3),
                                           auc_peak_ndvi_low=round(roc_auc_score(both.t[ok], -both.peak_ndvi[ok]), 3),
                                           no_harvest_rule_rate_without=round(both.harvest_doy[ok & (both.t == 1)].isna().mean(), 3),
                                           no_harvest_rule_rate_with=round(both.harvest_doy[ok & (both.t == 0)].isna().mean(), 3))
json.dump(R, open(f"results/{name}_a5_anomaly.json", "w"), indent=1)
print(json.dumps(R, indent=1))

# validation 2: blinded panels -- 30 top-2% anomalies + 30 random scored unit-years, shuffled
for col in ("traj_dev", "traj_dev_season", "emb_dev"):
    R[f"event_rule_auc_{col}"] = {k: round(roc_auc_score(F.loc[ar & F[col].notna(), k], F.loc[ar & F[col].notna(), col]), 3) for k in ("ev_low_peak", "ev_delayed_resown", "ev_no_harvest")}
json.dump(R, open(f"results/{name}_a5_anomaly.json", "w"), indent=1)
print(json.dumps({k: v for k, v in R.items() if k.startswith("event_rule")}, indent=1))
SCORE = sys.argv[4] if len(sys.argv) > 4 else "anomaly"
if len(sys.argv) > 3 and sys.argv[3] == "panels":
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    rng = np.random.default_rng(1)
    seed = 1 if SCORE == "anomaly" else 11
    sc = F[F[SCORE].notna() & ar]
    top = sc[sc[SCORE] >= sc[SCORE].quantile(.98)].sample(30, random_state=seed)
    rnd = sc[sc[SCORE] < sc[SCORE].quantile(.98)].sample(30, random_state=seed + 1)
    S = pd.concat([top.assign(kind="top"), rnd.assign(kind="random")]).sample(frac=1, random_state=seed + 2).reset_index(drop=True)
    fig, ax = plt.subplots(6, 10, figsize=(30, 15))
    for k, r in S.iterrows():
        a = ax.flat[k]
        lo, med, hi = curves[(r.year, r.hcat)]
        a.fill_between(GRID, lo, hi, color="0.85")
        a.plot(GRID, med, color="0.4", lw=1)
        a.plot(GRID, PH[str(r.year)][r.ui]["ndvi_smooth"], color="C3", lw=1.6)
        a.set_ylim(-0.1, 1)
        a.set_title(f"#{k} {r.hcat[:22]} {r.year}", fontsize=8)
        a.tick_params(labelsize=6)
    fig.tight_layout()
    fig.savefig(f"{D}/{name}/blind_panels_{SCORE}.png", dpi=55)
    S[["uid", "year", "hcat", "kind", SCORE]].to_csv(f"{D}/{name}/blind_key_{SCORE}.csv")
    print("panels written; key withheld at", f"{D}/{name}/blind_key_{SCORE}.csv")
