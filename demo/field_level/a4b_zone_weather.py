"""A4b: does the within-field terrain pattern change with the season's water supply?

Per unit-year (arable, >=30 px): Spearman of the pixel z (pheno.py) with TPI. Averaged per year,
then compared across years with the Apr-Jun climatic water balance (weather.py). Water
redistribution predicts hollows greener in dry seasons (more negative rho); waterlogging predicts
the hollow advantage shrinking or reversing in wet seasons. n = years per window (7 AT, 5 BB)."""

import json
import sys

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

name, D = sys.argv[1], sys.argv[2]
F = pd.read_csv(f"{D}/{name}/features.csv")
lab = np.load(f"{D}/{name}/pixel_lab.npy")
L = lab.ravel()
inside = L > 0
Li = L[inside] - 1
tpi = np.load(f"{D}/{name}/dem.npz")["tpi"].ravel()[inside]
order = np.argsort(Li, kind="stable")
starts = np.searchsorted(Li[order], np.arange(F.ui.max() + 2))
Wx = json.load(open(f"results/{name}_weather.json"))
ar = {"winter cereal", "spring cereal", "maize", "field veg", "potato", "sugar beet", "legume", "oilseed/pumpkin"}
rows = []
for y in sorted(F.year.unique()):
    z = np.load(f"{D}/{name}/pixel_{y}.npz")["z"]
    units = F[(F.year == y) & F.group.isin(ar)].ui.values
    rhos = []
    for u in units:
        px = order[starts[u]:starts[u + 1]]
        if len(px) < 30:
            continue
        zz, tt = z[px], tpi[px]
        ok = np.isfinite(zz) & (np.abs(zz) < 6)
        if ok.sum() >= 30 and np.ptp(tt[ok]) > 0.5:
            rhos.append(spearmanr(zz[ok], tt[ok]).statistic)
    rows.append(dict(year=int(y), n_units=len(rhos), mean_rho_tpi=round(float(np.mean(rhos)), 3), share_neg=round(float(np.mean(np.array(rhos) < 0)), 3),
                     cwb_aprjun=Wx["years"][str(y)]["cwb_aprjun"], cwb_pct=Wx["percentile_vs_normal"]["cwb_aprjun"][str(y)]))
R = dict(by_year=rows, spearman_rho_vs_cwb=round(float(spearmanr([r["cwb_aprjun"] for r in rows], [r["mean_rho_tpi"] for r in rows]).statistic), 3), n_years=len(rows))
json.dump(R, open(f"results/{name}_a4b_zone_weather.json", "w"), indent=1)
print(name, R["spearman_rho_vs_cwb"], [(r["year"], r["mean_rho_tpi"], r["cwb_aprjun"]) for r in rows])
