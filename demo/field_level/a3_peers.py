"""A3 peer benchmarking: field vs same-crop/same-year peers within 5 km, and how much of a
field's standing is a persistent field effect rather than a season effect.

z_peer (features.py) removes crop x year x neighbourhood. Persistence tests:
ICC of z across years (one-way ANOVA) vs a permutation null (z shuffled across units within year);
YoY Spearman; leave-one-year-out (mean of other years predicts this year); bottom-quartile
recurrence vs 25% chance; spatial control: correlation with the nearest other unit (<=500 m)."""

import json
import sys

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from scipy.stats import spearmanr

name, D = sys.argv[1], sys.argv[2]
F = pd.read_csv(f"{D}/{name}/features.csv")
rng = np.random.default_rng(0)
R = {}


def icc(df, col):
    g = df.groupby("uid")[col]
    k = g.count()
    df = df[df.uid.isin(k[k >= 3].index)]
    g = df.groupby("uid")[col]
    n, N = g.ngroups, len(df)
    m = df[col].mean()
    msb = (g.count() * (g.mean() - m) ** 2).sum() / (n - 1)
    msw = ((df[col] - g.transform("mean")) ** 2).sum() / (N - n)
    k0 = (N - (g.count() ** 2).sum() / N) / (n - 1)
    return (msb - msw) / (msb + (k0 - 1) * msw), n, N


for col in ("indvi_season_zpeer", "peak_ndvi_zpeer", "peak_doy_zpeer", "harvest_doy_zpeer"):
    d = F[F[col].notna() & F.group.isin(["winter cereal", "spring cereal", "maize", "field veg", "potato", "sugar beet", "legume", "oilseed/pumpkin"])][["uid", "year", "x", "y_", col]].copy()
    d[col] = d[col].clip(-5, 5)
    v, n, N = icc(d, col)
    null = []
    for _ in range(200):
        s = d.copy()
        s[col] = s.groupby("year")[col].transform(lambda x: rng.permutation(x.values))
        null.append(icc(s, col)[0])
    w = d.pivot_table(index="uid", columns="year", values=col)
    yrs = sorted(w.columns)
    yoy = [spearmanr(w[a], w[b], nan_policy="omit").statistic for a, b in zip(yrs, yrs[1:])]
    loo_r, q_rec = [], []
    for y in yrs:
        other = w.drop(columns=y).mean(1)
        ok = w[y].notna() & w.drop(columns=y).notna().sum(1).ge(2)
        loo_r.append(spearmanr(other[ok], w[y][ok]).statistic)
        q_rec.append(((other[ok] <= other[ok].quantile(.25)) & (w[y][ok] <= w[y][ok].quantile(.25))).sum() / (other[ok] <= other[ok].quantile(.25)).sum())
    # spatial control: same-year z of nearest other unit within 500 m
    nb = []
    for y, g in d.groupby("year"):
        t = cKDTree(g[["x", "y_"]].values)
        dist, idx = t.query(g[["x", "y_"]].values, k=2)
        ok = dist[:, 1] <= 500
        nb.append(spearmanr(g[col].values[ok], g[col].values[idx[ok, 1]]).statistic)
    R[col] = dict(n_units=n, n_unit_years=N, icc=round(v, 3), icc_null_p95=round(float(np.quantile(null, .95)), 3), yoy_spearman_median=round(float(np.median(yoy)), 3),
                  loyo_spearman_median=round(float(np.median(loo_r)), 3), bottom_quartile_recurrence=round(float(np.mean(q_rec)), 3), chance=0.25,
                  nearest_neighbour_same_year_spearman=round(float(np.median(nb)), 3))
# does persistence survive a crop change? z(Y) vs z(Y+1) only for pairs whose group changed
col = "indvi_season_zpeer"
d = F[F[col].notna()].set_index(["uid", "year"])
pairs = [(d.at[(u, y), col], d.at[(u, y + 1), col], d.at[(u, y), "group"] != d.at[(u, y + 1), "group"]) for u, y in d.index if (u, y + 1) in d.index]
P = pd.DataFrame(pairs, columns=["a", "b", "chg"]).clip(-5, 5)
R["indvi_persistence_across_crop_change"] = dict(n_changed=int(P.chg.sum()), spearman_changed=round(spearmanr(P.a[P.chg], P.b[P.chg]).statistic, 3),
                                                 n_same=int((~P.chg).sum()), spearman_same=round(spearmanr(P.a[~P.chg], P.b[~P.chg]).statistic, 3))
json.dump(R, open(f"results/{name}_a3_peers.json", "w"), indent=1)
print(json.dumps(R, indent=1))
