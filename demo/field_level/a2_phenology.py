"""A2 S2 phenology metrics, validated against crop type and declared multi-crop classes.

- harvest DOY vs an a-priori reference window per crop (typical Central-European calendar,
  set before looking at the data; +-10 d tolerance)
- >=2 complete cycles vs declared multi-crop vegetable classes
- winter cover after a summer harvest: green (Nov16-Dec31 NDVI >= 0.5) vs bare (< 0.3),
  split by next year's declaration (winter crop = autumn-sown, else cover/catch crop), and the
  embedding probe LOYO across years."""

import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, balanced_accuracy_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, os.path.dirname(__file__))
from common import ARABLE  # noqa: E402

name, D = sys.argv[1], sys.argv[2]
F = pd.read_csv(f"{D}/{name}/features.csv")
F = F[F.tracked & F.peak_ndvi.notna()]
R = {}
REF = {  # harvest window (DOY) by crop keyword, set a priori
    "WINTER BARLEY": (172, 195), "WINTER SOFT WHEAT": (180, 215), "DURUM": (180, 215), "WINTER RYE": (180, 215), "TRITICALE": (180, 215),
    "SUMMER BARLEY": (185, 220), "RAPE": (180, 205), "POTATO": (200, 275), "SUNFLOWER": (235, 275), "SOY": (250, 290),
    "GRAIN CORN": (255, 310), "SUGAR BEET": (255, 335), "winter_common_soft_wheat": (185, 225), "winter_barley": (175, 200),
    "winter_rapeseed": (185, 210), "grain_maize": (260, 310), "silage_maize": (240, 275), "winter_rye": (185, 220), "sugar_beet": (260, 335),
}
hv = []
for k, (a, b) in REF.items():
    m = F.hcat.str.contains(k, case=False, regex=False) & F.harvest_doy.notna()
    if m.sum() < 15:
        continue
    h = F.harvest_doy[m]
    hv.append(dict(crop=k, n=int(m.sum()), median=float(h.median()), iqr=[float(h.quantile(.25)), float(h.quantile(.75))], ref=[a, b],
                   within_10d=round(((h >= a - 10) & (h <= b + 10)).mean(), 3), detected_share=round(m.sum() / F.hcat.str.contains(k, case=False, regex=False).sum(), 3)))
R["harvest_vs_calendar"] = hv
if hv:
    from scipy.stats import spearmanr
    R["harvest_rank_corr_vs_ref_mid"] = round(spearmanr([x["median"] for x in hv], [np.mean(x["ref"]) for x in hv]).statistic, 3)
    w = np.array([x["n"] for x in hv])
    R["harvest_within_window_pooled"] = round(float(np.sum(w * np.array([x["within_10d"] for x in hv])) / w.sum()), 3)

veg = F[F.hcat.str.contains("VEGETABLES", na=False) & ~F.hcat.str.contains("GREENHOUSE|TUNNEL|WITHOUT", na=False)]
if len(veg):
    multi = veg.hcat.str.contains("MULTI", na=False)
    two = veg.n_cycles >= 2
    R["cycles_vs_multicrop"] = dict(n=len(veg), n_multi=int(multi.sum()), two_cycle_rate_multi=round(two[multi].mean(), 3), two_cycle_rate_single=round(two[~multi].mean(), 3),
                                    precision=round((two & multi).sum() / max(two.sum(), 1), 3), recall=round((two & multi).sum() / max(multi.sum(), 1), 3))
R["two_cycle_rate_by_group"] = F.groupby("group").apply(lambda g: round((g.n_cycles >= 2).mean(), 3)).to_dict()

# winter cover after summer harvest
nxt = F.set_index(["uid", "year"])
F["next_hcat"] = [nxt.hcat.get((u, y + 1)) for u, y in zip(F.uid, F.year)]
F["next_winter_early"] = [nxt.winter_early.get((u, y + 1)) for u, y in zip(F.uid, F.year)]
h = F[F.group.isin(ARABLE) & (F.harvest_doy <= 250) & (F.peak_ndvi >= 0.6)].copy()
h["wc"] = np.where(h.winter_late >= 0.5, 1, np.where(h.winter_late < 0.3, 0, -1))
hc = h[h.wc >= 0]
R["winter_cover"] = dict(n=len(hc), dropped_ambiguous=int((h.wc < 0).sum()), green_share=round(hc.wc.mean(), 3),
                         green_share_by_year=hc.groupby("year").wc.mean().round(3).to_dict())
pers = hc[hc.next_winter_early.notna()]
R["winter_cover"]["persistence_into_jan_feb"] = dict(n=len(pers), green_then_green=round((pers.next_winter_early[pers.wc == 1] >= 0.4).mean(), 3),
                                                     bare_then_green=round((pers.next_winter_early[pers.wc == 0] >= 0.4).mean(), 3))
g = hc[(hc.wc == 1) & hc.next_hcat.notna()].copy()
g["autumn_sown"] = g.next_hcat.str.contains("winter", case=False, na=False)
R["winter_cover"]["green_split_next_decl"] = dict(n=len(g), autumn_sown=int(g.autumn_sown.sum()), cover_catch=int((~g.autumn_sown).sum()))
R["winter_cover"]["bare_share_by_group"] = hc.groupby("group").apply(lambda x: [round(1 - x.wc.mean(), 3), len(x)]).to_dict()

# embedding probe for winter green after harvest, leave-one-year-out
T = np.load(f"{D}/{name}/tessera_units.npz")
yrs = list(T["years"])
E = T["means"] - T["aoi"][:, None, :]
X = np.stack([E[yrs.index(y), i] for y, i in zip(hc.year, hc.ui)])
okx = np.isfinite(X).all(1)
hcx, X = hc[okx], X[okx]
pe = np.zeros(len(hcx))
for y in sorted(hcx.year.unique()):
    tr, te = (hcx.year != y).values, (hcx.year == y).values
    if hcx.wc[tr].nunique() < 2 or hcx.wc[te].nunique() < 2:
        pe[te] = np.nan
        continue
    clf = make_pipeline(StandardScaler(), LogisticRegression(max_iter=3000, C=0.5, class_weight="balanced")).fit(X[tr], hcx.wc[tr])
    pe[te] = clf.predict_proba(X[te])[:, 1]
k = np.isfinite(pe)
R["winter_cover"]["embedding_loyo"] = dict(n=int(k.sum()), auc=round(roc_auc_score(hcx.wc[k], pe[k]), 3), bal_acc=round(balanced_accuracy_score(hcx.wc[k], pe[k] > 0.5), 3),
                                           auc_by_year={int(y): round(roc_auc_score(hcx.wc[k & (hcx.year == y).values], pe[k & (hcx.year == y).values]), 3) for y in sorted(hcx.year.unique()) if hcx.wc[k & (hcx.year == y).values].nunique() == 2})

# bare-soil days (erosion / nitrate-leaching exposure)
a = F[F.group.isin(ARABLE)]
R["bare_days_by_group"] = a.groupby("group").bare_days.describe()[["count", "25%", "50%", "75%"]].round(0).to_dict("index")
R["n_obs_per_unit_year"] = dict(median=float(F.n_obs.median()), p10=float(F.n_obs.quantile(.1)))
json.dump(R, open(f"results/{name}_a2_phenology.json", "w"), indent=1, default=str)
print(json.dumps(R, indent=1, default=str))
