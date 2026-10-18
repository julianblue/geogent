"""Per-pixel early- vs late-season vigour, z-scored within each unit-year.

Early = green-up to peak, late = peak to end of season of the unit's main crop (cycles_ts.py,
pheno.py as fallback). Only unit-dates where >=80% of the unit is clear (series_<y>.npz) count,
so every pixel of a unit is averaged over the same dates.
usage: python pixel_phases.py <window> <datadir> -> pixel_phase_<year>.npz (z_early, z_late; inside-pixel order)"""

import datetime as dt
import json
import sys

import numpy as np

name, D = sys.argv[1], sys.argv[2]
U = json.load(open(f"{D}/{name}/units.json"))
CY = json.load(open(f"{D}/{name}/cycles.json"))
PH = json.load(open(f"{D}/{name}/pheno.json"))
lab = np.load(f"{D}/{name}/pixel_lab.npy")
L = lab.ravel()
inside = L > 0
Li = L[inside] - 1
n = len(U["units"])
cnt = np.maximum(np.bincount(Li, minlength=n), 1)
for y in U["years"]:
    z = np.load(f"{D}/{name}/s2_{y}.npz")
    b = z["bands"]
    dates = [str(d) for d in z["dates"]]
    doy = np.array([dt.date.fromisoformat(d).timetuple().tm_yday for d in dates])
    ser = np.load(f"{D}/{name}/series_{y}.npz")["ndvi"]  # (t, units) NaN where <80% clear
    red = b[:, 2].reshape(len(dates), -1)[:, inside].astype("f4")
    nir = b[:, 4].reshape(len(dates), -1)[:, inside].astype("f4")
    nd = np.where(red > 0, (nir - red) / (nir + red + 1e-6), np.nan)
    sos = np.full(n, np.nan); pk = np.full(n, np.nan); eos = np.full(n, np.nan)
    for i in range(n):
        c = CY[str(y)][i] if str(y) in CY else None
        p = PH[str(y)][i]
        src = c if (c and "peak_doy" in c) else p
        if src:
            sos[i], pk[i], eos[i] = src["sos"], src["peak_doy"], src["eos"]
    out = {}
    for ph, (a, bnd) in {"early": (sos, pk), "late": (pk, eos)}.items():
        use = np.isfinite(ser) & (doy[:, None] >= a[None, :]) & (doy[:, None] <= bnd[None, :])  # (t, units)
        m = use[:, Li] & np.isfinite(nd)
        num = np.where(m, nd, 0).sum(0)
        den = m.sum(0)
        v = np.where(den >= 2, num / np.maximum(den, 1), np.nan).astype("f4")
        ok = np.isfinite(v)
        mu = np.bincount(Li[ok], weights=v[ok], minlength=n) / np.maximum(np.bincount(Li[ok], minlength=n), 1)
        sd = np.sqrt(np.bincount(Li[ok], weights=(v[ok] - mu[Li[ok]]) ** 2, minlength=n) / np.maximum(np.bincount(Li[ok], minlength=n), 1))
        out[f"z_{ph}"] = ((v - mu[Li]) / np.maximum(sd[Li], 1e-3)).astype("f4")
        out[f"n_{ph}"] = den.astype("i2")
    np.savez(f"{D}/{name}/pixel_phase_{y}.npz", **out)
    print(name, y, "pixels with early/late", int(np.isfinite(out["z_early"]).sum()), int(np.isfinite(out["z_late"]).sum()), flush=True)
