"""Per unit-year S2 phenology + per-pixel season layers (the window-scale equivalent of
geo/cube.py's productivity reduction) from the s2_<year>.npz cubes.

usage: python pheno.py <window> <datadir>
-> pheno.json  (unit-year metrics), series_<year>.npz (unit x date NDVI/NDRE/NDMI means),
   pixel_<year>.npz (per-pixel season-mean NDVI, within-unit z). Units are buffered 10 m
   inward (drops the 1-pixel edge). A unit-date counts if >=80% of its pixels are clear."""

import json
import os
import sys

import numpy as np
from rasterio.features import rasterize
from affine import Affine
from scipy.signal import find_peaks
from shapely import wkt

sys.path.insert(0, os.path.dirname(__file__))
from common import GRID, smooth  # noqa: E402

name, D = sys.argv[1], sys.argv[2]
U = json.load(open(f"{D}/{name}/units.json"))
units = U["units"]
n = len(units)
B = dict(blue=0, green=1, red=2, re1=3, nir=4, sw1=5, sw2=6)
out = {}
lab = None
for y in U["years"]:
    f = f"{D}/{name}/s2_{y}.npz"
    if not os.path.exists(f):
        continue
    z = np.load(f)
    dn = z["bands"]
    so = z["scale_offset"]
    dates = [str(d) for d in z["dates"]]
    doy = np.array([np.datetime64(d).astype("datetime64[D]").item().timetuple().tm_yday for d in dates])
    if lab is None:
        T = Affine(*z["transform"])
        geoms = [wkt.loads(u["wkt"]).buffer(-10) for u in units]
        lab = rasterize([(g, i + 1) for i, g in enumerate(geoms) if not g.is_empty], out_shape=dn.shape[2:], transform=T, fill=0, dtype="int32")
        L = lab.ravel()
        inside = L > 0
        Li = L[inside] - 1
        tot = np.bincount(Li, minlength=n)
    t_n = dn.shape[0]
    ser = {k: np.full((t_n, n), np.nan, "f4") for k in ("ndvi", "ndre", "ndmi")}
    pix_nd = np.full((t_n, inside.sum()), np.nan, "f4")
    for t in range(t_n):
        r = dn[t].reshape(7, -1)[:, inside].astype("f4")
        clear = r[B["red"]] > 0
        refl = r * 1e-4  # see s2_cube.py: stored scale_offset predates the offset fix; all items are offset-applied
        clear &= (refl[B["nir"]] + refl[B["red"]]) > 0.02
        def nd(a, b):
            return np.where(clear, np.clip((refl[a] - refl[b]) / (refl[a] + refl[b] + 1e-6), -1, 1), np.nan)
        idx = dict(ndvi=nd(B["nir"], B["red"]), ndre=nd(B["nir"], B["re1"]), ndmi=nd(B["nir"], B["sw1"]))
        pix_nd[t] = idx["ndvi"]
        cnt = np.bincount(Li[clear], minlength=n)
        good = cnt >= 0.8 * np.maximum(tot, 1)
        for k, v in idx.items():
            s = np.bincount(Li[clear], weights=v[clear], minlength=n)
            ser[k][t] = np.where(good & (tot >= 5), s / np.maximum(cnt, 1), np.nan)
    np.savez(f"{D}/{name}/series_{y}.npz", doy=doy, dates=np.array(dates), **ser)
    # unit-level phenology
    res = []
    season_mask = np.zeros((t_n, n), bool)
    for i in range(n):
        v = ser["ndvi"][:, i]
        ok = np.isfinite(v)
        s = smooth(doy, v)
        if s is None:
            res.append(None)
            continue
        near = np.min(np.abs(GRID[:, None] - doy[ok][None, :]), axis=1) <= 20
        win = (GRID >= 60) & (GRID <= 300)
        p = int(np.argmax(np.where(win, s, -9)))
        peak = float(s[p])
        bpre, bpost = float(s[: p + 1].min()), float(s[p:].min())
        ampre, ampost = peak - bpre, peak - bpost
        k = p
        while k > 0 and s[k - 1] >= bpre + 0.5 * ampre:
            k -= 1
        sos = int(GRID[k])
        k = p
        while k < len(GRID) - 1 and s[k + 1] >= bpost + 0.5 * ampost:
            k += 1
        eos = int(GRID[min(k + 1, len(GRID) - 1)])
        k = p
        while k < len(GRID) - 1 and s[k] > bpost + 0.2 * ampost:
            k += 1
        harvest = int(GRID[k]) if ampost >= 0.3 and s[k] <= bpost + 0.2 * ampost + 1e-6 else None
        pk, _ = find_peaks(np.r_[0, s, s[-1]], height=0.65, prominence=0.3, distance=8)
        pk = [q - 1 for q in pk if 60 <= GRID[min(q - 1, len(GRID) - 1)] <= 300 and q - 1 < len(GRID) - 3]
        above = np.clip(s - 0.2, 0, None) * 5
        insea = (GRID >= sos) & (GRID <= eos)
        nre = ser["ndre"][:, i]
        nmi = ser["ndmi"][:, i]
        dsea = (doy >= sos) & (doy <= eos) & ok
        season_mask[:, i] = dsea
        after_h = GRID >= (harvest or 999)
        res.append(dict(
            n_obs=int(ok.sum()), peak_ndvi=round(peak, 3), peak_doy=int(GRID[p]), sos=sos, eos=eos, season_len=eos - sos,
            harvest_doy=harvest, n_cycles=len(pk), cycle_peaks=[int(GRID[q]) for q in pk],
            indvi_year=round(float(above.sum()), 1), indvi_season=round(float(above[insea].sum()), 1),
            winter_late=round(float(s[GRID >= 320].mean()), 3), winter_early=round(float(s[GRID <= 45].mean()), 3),
            bare_days=int(((s < 0.3) & near).sum() * 5), bare_days_after_harvest=int(((s < 0.3) & near & after_h).sum() * 5),
            ndre_season=None if not dsea.any() else round(float(np.nanmean(nre[dsea])), 3),
            ndmi_season=None if not dsea.any() else round(float(np.nanmean(nmi[dsea])), 3),
            ndvi_smooth=[round(float(x), 3) for x in s],
        ))
    out[y] = res
    # per-pixel season-mean NDVI over the unit's in-season clear dates, and within-unit z
    sm = season_mask[:, Li]  # (t, px)
    num = np.nansum(np.where(sm, pix_nd, 0), 0)
    den = np.sum(sm & np.isfinite(pix_nd), 0)
    pm = np.where(den >= 3, num / np.maximum(den, 1), np.nan).astype("f4")
    ok = np.isfinite(pm)
    mu = np.bincount(Li[ok], weights=pm[ok], minlength=n) / np.maximum(np.bincount(Li[ok], minlength=n), 1)
    sd = np.sqrt(np.bincount(Li[ok], weights=(pm[ok] - mu[Li[ok]]) ** 2, minlength=n) / np.maximum(np.bincount(Li[ok], minlength=n), 1))
    zz = ((pm - mu[Li]) / np.maximum(sd[Li], 1e-3)).astype("f4")
    np.savez(f"{D}/{name}/pixel_{y}.npz", season_mean=pm, z=zz, n_dates=den.astype("i2"))
    print(name, y, t_n, "dates; units with phenology", sum(r is not None for r in res), flush=True)
np.save(f"{D}/{name}/pixel_lab.npy", lab)
json.dump(out, open(f"{D}/{name}/pheno.json", "w"))
