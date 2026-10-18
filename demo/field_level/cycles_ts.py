"""Crop-aware season metrics from the full multi-year NDVI series of each unit.

pheno.py takes the year's highest NDVI in DOY 60-300 as the main peak. When a post-harvest
catch crop outgrows a weak main crop (e.g. tr-115077081, 2024 barley 0.61 vs catch crop 0.67),
that picks the catch crop and the year reads as "late peak, no harvest". Here every unit's years
are stitched into one 5-day series, split into green cycles (peak >= 0.5, prominence >= 0.25), and
the cycle peaking inside the declared crop's window is the main crop; the rest are cover / catch
crops. Season bounds and harvest then use pheno.py's validated rules around that peak (a first
version took the steepest drop between clear scenes as harvest; it missed gradual cereal
senescence and dropped harvest-in-window from 92% to 73%).

usage: python cycles_ts.py <window> <datadir> -> cycles.json {year: [per-unit dict | None]}"""

import datetime as dt
import json
import os
import sys

import numpy as np
from scipy.signal import find_peaks, savgol_filter

sys.path.insert(0, os.path.dirname(__file__))
from common import group  # noqa: E402

# main-crop peak window (DOY) by group; groups not listed fall back to the naive 60-300 rule
WIN = {"winter cereal": (95, 175), "spring cereal": (140, 205), "maize": (185, 265), "sugar beet": (175, 275), "legume": (185, 265),
       "oilseed/pumpkin": (100, 265), "field veg": (120, 285), "potato": (150, 230)}

name, D = sys.argv[1], sys.argv[2]
U = json.load(open(f"{D}/{name}/units.json"))
years = U["years"]
t0 = dt.date(years[0], 1, 1)
tt, vv = [], []
for y in years:
    s = np.load(f"{D}/{name}/series_{y}.npz")
    tt.append(np.array([(dt.date.fromisoformat(str(d)) - t0).days for d in s["dates"]]))
    vv.append(s["ndvi"])
T, V = np.concatenate(tt), np.concatenate(vv)  # (dates,), (dates, units)
G = np.arange(0, (dt.date(years[-1], 12, 31) - t0).days + 1, 5)


def doy(t):
    return (t0 + dt.timedelta(int(t))).timetuple().tm_yday


def year_of(t):
    return (t0 + dt.timedelta(int(t))).year


out = {y: [None] * len(U["units"]) for y in years}
for i, u in enumerate(U["units"]):
    ok = np.isfinite(V[:, i])
    if ok.sum() < 8 * len(years):
        continue
    ti, vi = T[ok], V[ok, i]
    S = savgol_filter(np.interp(G, ti, vi), 7, 2)
    pk, _ = find_peaks(S, height=0.5, prominence=0.25, distance=8)
    cyc = []
    for k, p in enumerate(pk):
        lo = pk[k - 1] if k else 0
        hi = pk[k + 1] if k + 1 < len(pk) else len(S) - 1
        l = lo + int(np.argmin(S[lo:p + 1]))
        r = p + int(np.argmin(S[p:hi + 1]))
        a = p
        while a > l and S[a - 1] >= S[l] + 0.5 * (S[p] - S[l]):
            a -= 1
        b = p
        while b < r and S[b + 1] >= S[r] + 0.5 * (S[p] - S[r]):
            b += 1
        m = (ti >= G[p]) & (ti <= G[r] + 15)
        harv, gap = None, None
        if m.sum() > 1:
            dv = np.diff(vi[m])
            j = int(np.argmin(dv))
            if dv[j] <= -0.15:
                harv_t = (ti[m][j] + ti[m][j + 1]) / 2
                harv, gap = harv_t, int(ti[m][j + 1] - ti[m][j])
        auc = float(np.clip(S[a:b + 1] - 0.2, 0, None).sum() * 5)
        cyc.append(dict(p=int(G[p]), peak=float(S[p]), a=int(G[a]), b=int(G[b]), harv=harv, gap=gap, auc=auc, year=year_of(G[p])))
    for y in years:
        d = u["years"][str(y)]
        grp = group(d["hcat_code"], d["hcat"]) if d else None
        w = WIN.get(grp)
        if w is None:
            continue  # untracked or non-arable: keep pheno.py metrics
        ys = (dt.date(y, 1, 1) - t0).days
        in_year = [c for c in cyc if c["year"] == y]
        main = [c for c in in_year if w[0] <= doy(c["p"]) <= w[1]]
        if main:
            c = max(main, key=lambda c: c["auc"])
            p = int(np.searchsorted(G, c["p"]))
            found = "cycle"
        else:  # no prominent cycle in the window: fall back to the window maximum if it is green at all
            win = (G >= ys + w[0] - 1) & (G <= ys + w[1] - 1)
            p = int(np.flatnonzero(win)[np.argmax(S[win])])
            found = "weak" if S[p] >= 0.4 else "none"
            if found == "none":
                out[y][i] = dict(main_found=False, n_cover_cycles=sum(doy(c["p"]) > w[1] for c in in_year))
                continue
        # season bounds and harvest: same rules as pheno.py, but around the crop-window peak
        lo = max(0, p - 60)
        hi = min(len(S) - 1, p + 40)
        bpre, bpost = S[lo:p + 1].min(), S[p:hi + 1].min()
        k = p
        while k > lo and S[k - 1] >= bpre + 0.5 * (S[p] - bpre):
            k -= 1
        sos = G[k]
        k = p
        while k < hi and S[k + 1] >= bpost + 0.5 * (S[p] - bpost):
            k += 1
        eos = G[min(k + 1, hi)]
        k = p
        while k < hi and S[k] > bpost + 0.2 * (S[p] - bpost):
            k += 1
        harvest = G[k] if (S[p] - bpost) >= 0.3 and S[k] <= bpost + 0.2 * (S[p] - bpost) + 1e-6 else None
        yr = (G >= max(sos, ys)) & (G <= min(eos, ys + 364))
        out[y][i] = dict(main_found=found == "cycle", main_kind=found, peak_ndvi=round(float(S[p]), 3), peak_doy=doy(G[p]), sos=int(sos - ys + 1), eos=int(eos - ys + 1),
                         harvest_doy=None if harvest is None else int(harvest - ys + 1), harvest_gap_days=None,
                         indvi_season=round(float(np.clip(S[yr] - 0.2, 0, None).sum() * 5), 1),
                         n_cover_cycles=sum(c["p"] > G[p] + 30 for c in in_year), pre_cover=any(c["p"] < G[p] - 30 and c["year"] == y for c in in_year))
json.dump(out, open(f"{D}/{name}/cycles.json", "w"), default=int)
n = sum(x is not None for y in years for x in out[y])
from collections import Counter
print(name, "arable unit-years", n, Counter(("none" if not x["main_found"] and "main_kind" not in x else x["main_kind"]) for y in years for x in out[y] if x))
