"""A9: low-performing zones -- delineation, temporal hold-out, soil ground truth, and a typology
of *why* each zone is low.

Zone score = within-unit z of season-mean NDVI (pixel_<y>.npz), averaged over arable seasons and
3x3-smoothed inside the unit. Low patch = connected pixels (8-neighbour, >=10 px = 0.1 ha) with
score <= the unit's 20th percentile.

Hold-out: score from the training seasons (<= SPLIT) predicts the bottom-20% pixels of each later
season (AUC per unit-season), against a null that rotates the same score map 180 degrees inside
the unit (keeps spatial texture, breaks alignment).

Soil truth: AT = eBod polygons (soil.npz: usable field capacity, rooting depth, arable value);
BB = Bodenschaetzung pits (soil_pits.csv: Wertzahl). Within-field comparisons only.

Typology per low patch (rules, first match): edge/headland; legacy (former separate parcel 2015-18);
drought-prone (deficit grows in dry springs, or late-season dominated); wet / hollow (deficit grows
in wet springs, or sits low in the terrain with an early-season deficit); establishment (early-
season dominated); unexplained.
usage: python a9_zones_deep.py <window> <datadir>"""

import json
import os
import sys

import numpy as np
import pandas as pd
from scipy import ndimage
from scipy.stats import binomtest, spearmanr, wilcoxon
from shapely import wkt
from sklearn.metrics import roc_auc_score

sys.path.insert(0, os.path.dirname(__file__))
from common import ARABLE  # noqa: E402
from windows import WINDOWS  # noqa: E402

name, D = sys.argv[1], sys.argv[2]
W = WINDOWS[name]
SPLIT = 2022 if W["cc"] == "at" else 2021
F = pd.read_csv(f"{D}/{name}/features.csv")
U = json.load(open(f"{D}/{name}/units.json"))
units = U["units"]
years = U["years"]
lab = np.load(f"{D}/{name}/pixel_lab.npy")
H, Wd = lab.shape
Lr = lab.ravel()
inside_idx = np.flatnonzero(Lr > 0)
Li = Lr[inside_idx] - 1
order = np.argsort(Li, kind="stable")
starts = np.searchsorted(Li[order], np.arange(len(units) + 1))
Z = {y: np.load(f"{D}/{name}/pixel_{y}.npz") for y in years}
PHZ = {y: np.load(f"{D}/{name}/pixel_phase_{y}.npz") for y in years}
dem = np.load(f"{D}/{name}/dem.npz")
edge = ndimage.distance_transform_edt(lab > 0).ravel()[inside_idx]
Wx = json.load(open(f"results/{name}_weather.json"))
cwb_pct = {int(y): v for y, v in Wx["percentile_vs_normal"]["cwb_aprjun"].items()}
soil = np.load(f"{D}/{name}/soil.npz") if os.path.exists(f"{D}/{name}/soil.npz") else None
pits = pd.read_csv(f"{D}/{name}/soil_pits.csv") if os.path.exists(f"{D}/{name}/soil_pits.csv") else None
hist = json.load(open(f"{D}/{name}/parcels_utm_hist.json")) if os.path.exists(f"{D}/{name}/parcels_utm_hist.json") else {}
arable = F[F.group.isin(ARABLE)].groupby("ui").year.apply(set).to_dict()
T = np.load(f"{D}/{name}/s2_{years[0]}.npz", mmap_mode="r")["transform"]
x0, y0 = T[2], T[5]
rng = np.random.default_rng(0)

# former parcels 2015-18 rasterised per year (legacy boundaries)
legacy = {}
if hist:
    from rasterio.features import rasterize
    from affine import Affine
    for y, feats in hist.items():
        legacy[int(y)] = rasterize([(wkt.loads(f["wkt"]), k + 1) for k, f in enumerate(feats)], out_shape=(H, Wd), transform=Affine(*T), fill=0, dtype="int32").ravel()[inside_idx]

patches, holdout, soil_rows, pit_rows = [], [], [], []
for ui in range(len(units)):
    px = order[starts[ui]:starts[ui + 1]]
    yrs = sorted(y for y in arable.get(ui, ()) if y in Z)
    if len(px) < 30 or len(yrs) < 4:
        continue
    rr, cc = np.divmod(inside_idx[px], Wd)
    r0, c0 = rr.min(), cc.min()
    grid = np.full((rr.max() - r0 + 1, cc.max() - c0 + 1), np.nan)

    def smooth(v):
        g = grid.copy()
        g[rr - r0, cc - c0] = v
        m = np.isfinite(g)
        num = ndimage.uniform_filter(np.where(m, g, 0), 3)
        den = ndimage.uniform_filter(m.astype(float), 3)
        return np.where(m, num / np.maximum(den, 1e-6), np.nan)[rr - r0, cc - c0]

    M = np.stack([Z[y]["z"][px] for y in yrs]).astype(float)
    M[np.abs(M) > 6] = np.nan
    # ---- hold-out
    tr = [k for k, y in enumerate(yrs) if y <= SPLIT]
    te = [k for k, y in enumerate(yrs) if y > SPLIT]
    if len(tr) >= 3 and te:
        s_tr = smooth(np.nanmean(M[tr], 0))
        rot = np.full_like(s_tr, np.nan)
        g = grid.copy(); g[rr - r0, cc - c0] = s_tr; g = g[::-1, ::-1]
        rot = g[rr - r0, cc - c0]
        for k in te:
            t = M[k]
            ok = np.isfinite(t) & np.isfinite(s_tr)
            low = t <= np.nanpercentile(t, 20)
            if ok.sum() >= 30 and 0 < low[ok].sum() < ok.sum():
                okr = ok & np.isfinite(rot)
                yr = yrs[k]
                holdout.append(dict(ui=ui, year=yr, group=F[(F.ui == ui) & (F.year == yr)].group.iloc[0], n_px=int(ok.sum()),
                                    auc=roc_auc_score(low[ok], -s_tr[ok]), auc_null=roc_auc_score(low[okr], -rot[okr]) if okr.sum() >= 30 and 0 < low[okr].sum() < okr.sum() else np.nan,
                                    deficit_in_test=float(np.nanmean(t[s_tr <= np.nanpercentile(s_tr, 20)]))))
    # ---- full-history zones
    score = smooth(np.nanmean(M, 0))
    q20 = np.nanpercentile(score, 20)
    lowmask = score <= q20
    g = np.zeros(grid.shape, bool); g[rr - r0, cc - c0] = lowmask
    labs, nlab = ndimage.label(g, structure=np.ones((3, 3)))
    plab = labs[rr - r0, cc - c0]
    nd_mean = np.stack([Z[y]["season_mean"][px] for y in yrs]).astype(float)
    ze = np.stack([PHZ[y]["z_early"][px] for y in yrs]).astype(float)
    zl = np.stack([PHZ[y]["z_late"][px] for y in yrs]).astype(float)
    tpi = dem["tpi"].ravel()[inside_idx[px]]
    twi = dem["twi"].ravel()[inside_idx[px]]
    elev = dem["dem"].ravel()[inside_idx[px]]
    e = edge[px]
    for k in range(1, nlab + 1):
        m = plab == k
        if m.sum() < 10:
            continue
        rest = ~m & np.isfinite(score)
        per_season = np.nanmean(M[:, m], 1)
        cw = np.array([cwb_pct[y] for y in yrs])
        rho_w = spearmanr(cw, per_season).statistic if len(yrs) >= 4 else np.nan
        early, late = float(np.nanmean(ze[:, m])), float(np.nanmean(zl[:, m]))
        rec = dict(uid=units[ui]["uid"], ui=ui, patch=k, n_px=int(m.sum()), ha=round(m.sum() * 0.01, 2), field_share=round(float(m.mean()), 3), n_seasons=len(yrs),
                   deficit_z=float(np.nanmean(score[m])), deficit_ndvi=float(np.nanmean(nd_mean[:, m]) - np.nanmean(nd_mean[:, rest])),
                   low_recurrence=float(np.nanmean(M[:, m] <= np.nanpercentile(M, 20, axis=1, keepdims=True))),
                   edge_share=float((e[m] <= 2).mean()), edge_share_field=float((e <= 2).mean()),
                   tpi_off=float(np.nanmean(tpi[m]) - np.nanmean(tpi)), elev_off=float(np.nanmean(elev[m]) - np.nanmean(elev)), twi_off=float(np.nanmean(twi[m]) - np.nanmean(twi)),
                   z_early=early, z_late=late, rho_water=float(rho_w),
                   cx=float(x0 + 10 * (cc[m].mean() + 0.5)), cy=float(y0 - 10 * (rr[m].mean() + 0.5)))
        # legacy: one former parcel holds >=80% of the patch and the field was split then
        rec["legacy"] = False
        for ly, lp in legacy.items():
            ids = lp[px]
            vals, cnts = np.unique(ids[ids > 0], return_counts=True)
            if len(vals) >= 2 and (cnts / len(ids) >= 0.15).sum() >= 2:
                pv, pcnt = np.unique(ids[m], return_counts=True)
                main = pv[np.argmax(pcnt)]
                if main > 0 and pcnt.max() / m.sum() >= 0.8 and (ids == main).sum() / len(ids) <= 0.6:
                    rec["legacy"] = True
                    rec["legacy_year"] = ly
                    break
        if soil is not None:
            for key, col in (("nfk", "nutzbare_feldkapazitaet"), ("depth", "gruendigkeit"), ("acker", "ackerwert")):
                v = soil[col].ravel()[inside_idx[px]]
                rec[f"soil_{key}_off"] = float(np.nanmean(v[m]) - np.nanmean(v[rest])) if np.isfinite(v[m]).any() and np.isfinite(v[rest]).any() else np.nan
                rec[f"soil_{key}_varies"] = bool(np.nanstd(v) > 0)
        patches.append(rec)
    # ---- soil truth, within-field (whole score map, not just patches)
    if soil is not None:
        for key, col in (("nfk", "nutzbare_feldkapazitaet"), ("depth", "gruendigkeit"), ("acker", "ackerwert")):
            v = soil[col].ravel()[inside_idx[px]]
            ok = np.isfinite(v) & np.isfinite(score)
            if ok.sum() >= 30 and len(np.unique(v[ok])) >= 2:
                vals = np.unique(v[ok])
                hi, lo = v[ok] == vals.max(), v[ok] == vals.min()
                if hi.sum() >= 10 and lo.sum() >= 10:
                    sc = score[ok]
                    soil_rows.append(dict(ui=ui, attr=key, diff=float(sc[hi].mean() - sc[lo].mean()), gap=float(vals.max() - vals.min()), n_hi=int(hi.sum()), n_lo=int(lo.sum()),
                                          rho=float(spearmanr(v[ok], sc).statistic)))
    if pits is not None:
        # pits inside this unit: score at the pit (3x3 mean already)
        cx_, cy_ = ((pits.x - x0) / 10).astype(int), ((y0 - pits.y) / 10).astype(int)
        inu = (cy_ >= 0) & (cy_ < H) & (cx_ >= 0) & (cx_ < Wd)
        idx = np.full(len(pits), -1)
        flat = (cy_[inu] * Wd + cx_[inu]).values
        pos = np.searchsorted(inside_idx[px], flat)
        hit = (pos < len(px)) & (inside_idx[px][np.minimum(pos, len(px) - 1)] == flat)
        for j, (pp, h) in enumerate(zip(np.flatnonzero(inu.values), hit)):
            if h and pits.kultur.iloc[pp] == "A" and np.isfinite(pits.wertzahl.iloc[pp]):
                k = np.searchsorted(inside_idx[px], flat[j])
                pit_rows.append(dict(ui=ui, pit=pits.id.iloc[pp], wertzahl=pits.wertzahl.iloc[pp], bodenart=pits.bodenart.iloc[pp], score=float(score[k]), low=bool(lowmask[k])))

P = pd.DataFrame(patches)
HO = pd.DataFrame(holdout)
SR = pd.DataFrame(soil_rows)
PR = pd.DataFrame(pit_rows)


def classify(r):
    if r.edge_share >= 0.6 and r.edge_share >= r.edge_share_field + 0.25:
        return "edge / headland"
    if r.legacy:
        return "legacy parcel"
    if (np.isfinite(r.rho_water) and r.rho_water >= 0.5) or (r.z_late - r.z_early <= -0.3):
        return "drought-prone"
    if (np.isfinite(r.rho_water) and r.rho_water <= -0.5) or (r.tpi_off <= -0.3 and r.z_early - r.z_late <= -0.3):
        return "wet / hollow"
    if r.z_early - r.z_late <= -0.3:
        return "establishment"
    return "unexplained"


P["type"] = P.apply(classify, axis=1)
P.to_csv(f"{D}/{name}/zones_deep.csv", index=False)
R = dict(window=name, split_year=SPLIT, n_units_with_patches=int(P.uid.nunique()) if len(P) else 0, n_patches=len(P))
if len(HO):
    R["holdout"] = dict(n_unit_seasons=len(HO), auc_median=round(float(HO.auc.median()), 3), auc_null_median=round(float(HO.auc_null.median()), 3),
                        share_auc_gt_0_6=round(float((HO.auc > 0.6).mean()), 3), share_null_gt_0_6=round(float((HO.auc_null > 0.6).mean()), 3),
                        low_zone_mean_z_in_test=round(float(HO.deficit_in_test.mean()), 3),
                        by_group={g: [round(float(x.auc.median()), 3), len(x)] for g, x in HO.groupby("group") if len(x) >= 30})
if len(P):
    R["patches"] = dict(median_ha=float(P.ha.median()), median_field_share=float(P.field_share.median()), deficit_ndvi_median=round(float(P.deficit_ndvi.median()), 3),
                        deficit_ndvi_p10=round(float(P.deficit_ndvi.quantile(.1)), 3), recurrence_median=round(float(P.low_recurrence.median()), 3),
                        type_share={k: round(float(v), 3) for k, v in P.type.value_counts(normalize=True).items()},
                        type_ha={k: round(float(v), 1) for k, v in P.groupby("type").ha.sum().items()})
if len(SR):
    R["soil_within_field"] = {}
    for a, g in SR.groupby("attr"):
        R["soil_within_field"][a] = dict(n_fields=len(g), mean_score_diff_hi_minus_lo=round(float(g["diff"].mean()), 3),
                                         share_positive=round(float((g["diff"] > 0).mean()), 3), sign_test_p=float(binomtest(int((g["diff"] > 0).sum()), len(g)).pvalue),
                                         wilcoxon_p=float(wilcoxon(g["diff"]).pvalue) if len(g) >= 10 else None, median_rho=round(float(g.rho.median()), 3))
    if soil is not None and len(P):
        for t, g in P.groupby("type"):
            sub = g[g.soil_nfk_varies == True]  # noqa: E712
            if len(sub) >= 8:
                R.setdefault("patch_soil_by_type", {})[t] = dict(n=len(sub), nfk_off_mean=round(float(sub.soil_nfk_off.mean()), 1), share_nfk_lower=round(float((sub.soil_nfk_off < 0).mean()), 3),
                                                                 depth_off_mean=round(float(sub.soil_depth_off.mean()), 2), acker_off_mean=round(float(sub.soil_acker_off.mean()), 2))
if len(PR):
    multi = PR.groupby("ui").filter(lambda x: len(x) >= 2 and x.wertzahl.nunique() >= 2)
    d = multi.assign(sc=multi.score - multi.groupby("ui").score.transform("mean"), wz=multi.wertzahl - multi.groupby("ui").wertzahl.transform("mean"))
    R["pits"] = dict(n_pits_in_fields=len(PR), n_fields_multi=int(multi.ui.nunique()), n_pits_multi=len(multi),
                     within_field_spearman=round(float(spearmanr(d.wz, d.sc).statistic), 3) if len(d) >= 10 else None,
                     within_field_p=float(spearmanr(d.wz, d.sc).pvalue) if len(d) >= 10 else None,
                     wertzahl_low_vs_other=[round(float(PR[PR.low].wertzahl.mean()), 1), round(float(PR[~PR.low].wertzahl.mean()), 1), int(PR.low.sum()), int((~PR.low).sum())],
                     pooled_spearman=round(float(spearmanr(PR.wertzahl, PR.score).statistic), 3))
json.dump(R, open(f"results/{name}_a9_zones_deep.json", "w"), indent=1, default=float)
print(json.dumps(R, indent=1, default=float))
