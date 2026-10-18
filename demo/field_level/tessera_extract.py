"""TESSERA v1.1 per-unit mean embeddings for a window, every year.

Run with the backend venv of a feat/tessera-p1 worktree (icechunk/xarray), e.g.
  <worktree>/apps/backend/.venv/bin/python tessera_extract.py marchfeld <datadir>
Writes <datadir>/<window>/tessera_units.npz: means (year, unit, 128) float32 over the unit
buffered 10 m inward, counts (year, unit), disp (year, unit) = mean pixel distance to the unit
mean, aoi (year, 128) window mean. Derived embedding rasters stay in scratch (licence open)."""

import json
import os
import sys
import time

import numpy as np
from rasterio.features import rasterize
from shapely import wkt

from geogent_backend.geo.tessera import IcechunkTesseraReader

sys.path.insert(0, os.path.dirname(__file__))
from windows import WINDOWS  # noqa: E402

name, D = sys.argv[1], sys.argv[2]
HIST = [int(y) for y in sys.argv[3:]]  # e.g. 2017 2018 -> tessera_units_hist.npz, no pixel dumps
W = WINDOWS[name]
U = json.load(open(f"{D}/{name}/units.json"))
geoms = [wkt.loads(u["wkt"]).buffer(-10) for u in U["units"]]
r = IcechunkTesseraReader(year_threads=1)
n = len(geoms)
means, counts, disps, aoi = [], [], [], []
for y in HIST or U["years"]:
    t = time.time()
    w = r.read_window(W["bbox"], [y], 128)
    emb = w.emb[0]
    H, Wd = emb.shape[1:]
    valid = np.isfinite(emb).all(0).ravel()
    X = emb.reshape(128, -1).T
    aoi.append(X[valid].mean(0))
    lab = rasterize([(g, i + 1) for i, g in enumerate(geoms) if not g.is_empty], out_shape=(H, Wd), transform=w.transform, fill=0, dtype="int32").ravel()
    m = (lab > 0) & valid
    L = lab[m] - 1
    cnt = np.bincount(L, minlength=n)
    s = np.zeros((n, 128))
    np.add.at(s, L, X[m])
    mu = s / np.maximum(cnt, 1)[:, None]
    d = np.bincount(L, weights=np.linalg.norm(X[m] - mu[L], axis=1), minlength=n) / np.maximum(cnt, 1)
    mu[cnt == 0] = np.nan
    means.append(mu.astype("f4"))
    counts.append(cnt)
    disps.append(d.astype("f4"))
    if not HIST:
        np.savez(f"{D}/{name}/tessera_px_{y}.npz", emb=emb.astype("f2"), transform=np.array(w.transform)[:6], crs=str(w.crs))
    print(name, y, f"{H}x{Wd}", "valid", round(valid.mean(), 3), "units with px", int((cnt >= 5).sum()), "read", round(time.time() - t, 1), "s", flush=True)
np.savez(f"{D}/{name}/tessera_units{'_hist' if HIST else ''}.npz", means=np.stack(means), counts=np.stack(counts), disp=np.stack(disps), aoi=np.stack(aoi), years=np.array(HIST or U["years"]))
