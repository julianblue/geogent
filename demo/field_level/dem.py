"""Copernicus DEM GLO-30 on the window's 10 m S2 grid (bilinear) + slope, TPI(150 m), D8 TWI.

usage: python dem.py <window> <datadir> -> dem.npz. Licence: Copernicus DEM GLO-30, free
(ESA/Airbus, attribution 'produced using Copernicus WorldDEM-30')."""

import os
import sys

import numpy as np
import rasterio
from affine import Affine
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from scipy.ndimage import uniform_filter

sys.path.insert(0, os.path.dirname(__file__))
from windows import WINDOWS  # noqa: E402

name, D = sys.argv[1], sys.argv[2]
W = WINDOWS[name]
z = np.load(f"{D}/{name}/s2_{2019}.npz", mmap_mode="r")
T = Affine(*z["transform"])
H, Wd = z["bands"].shape[2:]
tile = f"Copernicus_DSM_COG_10_{W['dem']}_DEM"
url = f"https://copernicus-dem-30m.s3.amazonaws.com/{tile}/{tile}.tif"
with rasterio.open(url) as src, WarpedVRT(src, crs=f"EPSG:{W['epsg']}", transform=T, width=Wd, height=H, resampling=Resampling.bilinear) as v:
    dem = v.read(1).astype("f8")
gy, gx = np.gradient(dem, 10)
slope = np.degrees(np.arctan(np.hypot(gx, gy)))
tpi = dem - uniform_filter(dem, 31)
# D8 flow accumulation, cells processed from highest to lowest
acc = np.ones_like(dem)
pad = np.pad(dem, 1, constant_values=np.inf)
nbr = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
drops = np.stack([(dem - pad[1 + dy:1 + dy + H, 1 + dx:1 + dx + Wd]) / (np.hypot(dy, dx) * 10) for dy, dx in nbr])
best = drops.argmax(0)
has = drops.max(0) > 0
order = np.argsort(-dem, axis=None)
fa = acc.ravel()
tgt = np.full(H * Wd, -1)
rr, cc = np.divmod(np.arange(H * Wd), Wd)
dy = np.array([d[0] for d in nbr])[best.ravel()]
dx = np.array([d[1] for d in nbr])[best.ravel()]
ok = has.ravel() & (rr + dy >= 0) & (rr + dy < H) & (cc + dx >= 0) & (cc + dx < Wd)
tgt[ok] = ((rr + dy) * Wd + cc + dx)[ok]
for k in order:
    t = tgt[k]
    if t >= 0:
        fa[t] += fa[k]
twi = np.log(fa.reshape(H, Wd) * 10 / np.tan(np.radians(np.maximum(slope, 0.1))))
np.savez(f"{D}/{name}/dem.npz", dem=dem.astype("f4"), slope=slope.astype("f4"), tpi=tpi.astype("f4"), twi=twi.astype("f4"))
print(name, "dem range", round(dem.min(), 1), round(dem.max(), 1), "slope p50/p95", np.percentile(slope, [50, 95]).round(2), "TPI sd", round(tpi.std(), 2))
