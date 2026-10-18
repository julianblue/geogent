"""Window-level Sentinel-2 L2A pixel cube: raw DN for 7 bands + SCL, one scene per date,
warped onto one canonical 10 m UTM grid (same rule as geo/cube.py).

usage: python s2_cube.py <window> <year> <outdir>
Writes <outdir>/<window>/s2_<year>.npz: bands (t,7,H,W) uint16 with 0 where SCL not in {4,5},
plus dates, transform. Reflectance = DN * 1e-4: on `earthsearch:boa_offset_applied` items the
pixels already have the BOA offset removed (dense-canopy red DN p0.1 ~ 110-270), although
STAC `raster:bands` still advertises offset -0.1 -- honouring it shifts reflectance by -0.1."""

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import rasterio
from affine import Affine
from pyproj import Transformer
from pystac_client import Client
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT

sys.path.insert(0, os.path.dirname(__file__))
from windows import WINDOWS  # noqa: E402

BANDS = ("blue", "green", "red", "rededge1", "nir", "swir16", "swir22")
name, year, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
W = WINDOWS[name]
os.makedirs(f"{out}/{name}", exist_ok=True)
os.environ.update(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MULTIRANGE="YES", GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES", VSI_CACHE="TRUE")

t = Transformer.from_crs(4326, W["epsg"], always_xy=True)
b = W["bbox"]
xs, ys = zip(*[t.transform(x, y) for x in b[0::2] for y in b[1::2]])
x0, y1 = np.floor(min(xs) / 10) * 10, np.ceil(max(ys) / 10) * 10
width, height = int(np.ceil((max(xs) - x0) / 10)), int(np.ceil((y1 - min(ys)) / 10))
transform = Affine(10, 0, x0, 0, -10, y1)
vrt_opts = dict(crs=f"EPSG:{W['epsg']}", transform=transform, width=width, height=height, resampling=Resampling.nearest)

cat = Client.open("https://earth-search.aws.element84.com/v1")
items = list(cat.search(collections=["sentinel-2-l2a"], bbox=b, datetime=f"{year}-01-01/{year}-12-31", query={"eo:cloud_cover": {"lt": 70}}).items())
byday = {}
for it in items:  # one item per day: prefer the reprocessed (offset-applied) item, then lowest cloud
    d = it.datetime.date()
    key = (not it.properties.get("earthsearch:boa_offset_applied", False), it.properties["eo:cloud_cover"])
    if d not in byday or key < byday[d][0]:
        byday[d] = (key, it)
days = sorted(byday)
print(name, year, len(items), "items", len(days), "dates", f"grid {height}x{width}", flush=True)


def read(d):
    it = byday[d][1]
    try:
        with rasterio.open(it.assets["scl"].href) as src, WarpedVRT(src, **vrt_opts) as v:
            scl = v.read(1)
        clear = np.isin(scl, (4, 5))
        if clear.mean() < 0.02:
            return d, None, None
        arr = np.zeros((len(BANDS), height, width), np.uint16)
        for k, band in enumerate(BANDS):
            with rasterio.open(it.assets[band].href) as src, WarpedVRT(src, **vrt_opts) as v:
                arr[k] = v.read(1)
        arr[:, ~clear] = 0
        applied = it.properties.get("earthsearch:boa_offset_applied", False)
        base = float(it.properties.get("s2:processing_baseline", "0") or 0)
        return d, arr, (1e-4, -0.1 if (base >= 4 and not applied) else 0.0)
    except Exception as e:  # noqa: BLE001
        print("fail", d, e, flush=True)
        return d, None, None


t0 = time.time()
stack, kept, so = [], [], []
with ThreadPoolExecutor(8) as ex:
    for d, arr, s in ex.map(read, days):
        if arr is None:
            continue
        stack.append(arr)
        kept.append(str(d))
        so.append(s)
print("kept", len(kept), "dates in", round(time.time() - t0), "s", flush=True)
np.savez(f"{out}/{name}/s2_{year}.npz", bands=np.stack(stack), dates=np.array(kept), scale_offset=np.array(so), transform=np.array(transform)[:6], epsg=W["epsg"])
json.dump(dict(dates=kept, n_items=len(items)), open(f"{out}/{name}/s2_{year}.json", "w"))
