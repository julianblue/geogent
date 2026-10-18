"""A4 within-field variability: multi-season pixel zones, their stability, persistent low vigour,
and terrain explanation.

Per pixel and year: season-mean NDVI over the unit's in-season clear dates, z-scored within the
unit (pheno.py; 10 m inward buffer drops the edge pixel). Unit-years used: declared arable,
>=30 px. Controls: (1) edge effect -- z regressed on distance-to-boundary per unit-year and the
stability recomputed on residuals; (2) persistent-low recurrence vs the binomial expectation under
independence; (3) terrain rho vs a 180-degree-rotated-DEM null that keeps spatial autocorrelation."""

import json
import os
import sys

import numpy as np
import pandas as pd
from scipy.ndimage import distance_transform_edt
from scipy.stats import binom, spearmanr

sys.path.insert(0, os.path.dirname(__file__))
from common import ARABLE  # noqa: E402

name, D = sys.argv[1], sys.argv[2]
F = pd.read_csv(f"{D}/{name}/features.csv")
lab = np.load(f"{D}/{name}/pixel_lab.npy")
H, W = lab.shape
L = lab.ravel()
inside = L > 0
Li = L[inside] - 1
n_units = int(L.max())
years = sorted(F.year.unique())
Z = {y: np.load(f"{D}/{name}/pixel_{y}.npz")["z"] for y in years if os.path.exists(f"{D}/{name}/pixel_{y}.npz")}
dem = np.load(f"{D}/{name}/dem.npz") if os.path.exists(f"{D}/{name}/dem.npz") else None
edge = distance_transform_edt(lab > 0).ravel()[inside]  # px to the (buffered) unit boundary
order = np.argsort(Li, kind="stable")
starts = np.searchsorted(Li[order], np.arange(n_units + 1))
uid_of = F.drop_duplicates("ui").set_index("ui").uid
use = F[F.group.isin(ARABLE)].groupby("ui").year.apply(set).to_dict()
rows, zone_maps = [], {}
for ui in range(n_units):
    px = order[starts[ui]:starts[ui + 1]]
    yrs = sorted(y for y in use.get(ui, ()) if y in Z)
    if len(px) < 30 or len(yrs) < 3:
        continue
    M = np.stack([Z[y][px] for y in yrs])  # (years, px)
    M[np.abs(M) > 6] = np.nan
    good = np.isfinite(M).mean(1) > 0.8
    M, yrs = M[good], [y for y, g in zip(yrs, good) if g]
    if len(yrs) < 3:
        continue
    e = edge[px]
    # edge control: remove per-year dependence on distance-to-edge (binned means)
    bins = np.minimum(e, 6).astype(int)
    Mr = M.copy()
    for k in range(len(yrs)):
        for b in np.unique(bins):
            m = bins == b
            Mr[k, m] -= np.nanmean(M[k, m])
    def stab(A):
        rs = [spearmanr(A[i], A[j], nan_policy="omit").statistic for i in range(len(A)) for j in range(i + 1, len(A))]
        return float(np.nanmedian(rs))
    mz = np.nanmean(M, 0)
    half = spearmanr(np.nanmean(M[0::2], 0), np.nanmean(M[1::2], 0), nan_policy="omit").statistic
    low = (M <= np.nanquantile(M, 0.2, axis=1, keepdims=True))
    nval = np.isfinite(M).sum(0)
    need = np.ceil(0.6 * nval)
    pers_low = (low.sum(0) >= need) & (nval >= 3)
    exp_low = float(np.mean([binom.sf(k - 1, n, 0.2) for n, k in zip(nval, need)]))
    r = dict(ui=ui, uid=uid_of.get(ui), n_px=len(px), n_years=len(yrs), stability=stab(M), stability_edge_removed=stab(Mr), split_half=float(half),
             edge_rho=float(spearmanr(mz, e, nan_policy="omit").statistic), persistent_low_frac=float(pers_low.mean()), persistent_low_expected=exp_low)
    if dem is not None:
        for k in ("dem", "tpi", "twi", "slope"):
            v = dem[k].ravel()[inside][px]
            r[f"rho_{k}"] = float(spearmanr(mz, v, nan_policy="omit").statistic)
            # rotated null: 180-degree rotation of the unit's bbox raster
            rr, cc = np.divmod(np.flatnonzero(inside)[px], W)
            r0, r1, c0, c1 = rr.min(), rr.max(), cc.min(), cc.max()
            rot = dem[k][r0:r1 + 1, c0:c1 + 1][::-1, ::-1]
            vv = rot[rr - r0, cc - c0]
            r[f"rho_{k}_null"] = float(spearmanr(mz, vv, nan_policy="omit").statistic)
        r["relief_m"] = float(np.ptp(dem["dem"].ravel()[inside][px]))
    rows.append(r)
    zone_maps[ui] = (px, mz, pers_low)
Zs = pd.DataFrame(rows)
Zs.to_csv(f"{D}/{name}/zones.csv", index=False)
np.savez(f"{D}/{name}/zone_maps.npz", **{f"u{k}": np.stack([v[0], v[1], v[2]]) for k, v in zone_maps.items()})
R = dict(n_units=len(Zs), median_years=float(Zs.n_years.median()), median_px=float(Zs.n_px.median()),
         stability_median=round(Zs.stability.median(), 3), stability_edge_removed_median=round(Zs.stability_edge_removed.median(), 3),
         stability_iqr=[round(Zs.stability.quantile(.25), 3), round(Zs.stability.quantile(.75), 3)],
         share_units_stability_gt_0_3=round((Zs.stability > 0.3).mean(), 3), split_half_median=round(Zs.split_half.median(), 3),
         edge_rho_median=round(Zs.edge_rho.median(), 3), persistent_low_frac_median=round(Zs.persistent_low_frac.median(), 3),
         persistent_low_frac_mean=round(Zs.persistent_low_frac.mean(), 3), persistent_low_expected_mean=round(Zs.persistent_low_expected.mean(), 4),
         share_units_persistent_low_ge_10pct=round((Zs.persistent_low_frac >= 0.10).mean(), 3))
if dem is not None:
    for k in ("dem", "tpi", "twi", "slope"):
        R[f"terrain_{k}"] = dict(median_rho=round(Zs[f"rho_{k}"].median(), 3), median_abs_rho=round(Zs[f"rho_{k}"].abs().median(), 3),
                                 null_median_abs_rho=round(Zs[f"rho_{k}_null"].abs().median(), 3), share_abs_rho_gt_0_3=round((Zs[f"rho_{k}"].abs() > 0.3).mean(), 3),
                                 null_share_abs_rho_gt_0_3=round((Zs[f"rho_{k}_null"].abs() > 0.3).mean(), 3), share_negative=round((Zs[f"rho_{k}"] < 0).mean(), 3),
                                 null_share_negative=round((Zs[f"rho_{k}_null"] < 0).mean(), 3))
    hi = Zs[Zs.relief_m >= Zs.relief_m.quantile(.75)]
    R["terrain_top_relief_quartile"] = dict(n=len(hi), relief_m_min=round(hi.relief_m.min(), 1), median_rho_dem=round(hi.rho_dem.median(), 3), median_rho_twi=round(hi.rho_twi.median(), 3),
                                            median_abs_rho_dem=round(hi.rho_dem.abs().median(), 3), null_median_abs_rho_dem=round(hi.rho_dem_null.abs().median(), 3))
    R["relief_m_median"] = round(Zs.relief_m.median(), 1)
json.dump(R, open(f"results/{name}_a4_zones.json", "w"), indent=1)
print(json.dumps(R, indent=1))
