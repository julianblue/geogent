"""Austrian soil map (eBod, BFW; free to embed with attribution, 1:25,000 from 1:10,000 field
survey) from the public vector tiles, rasterised onto the window's 10 m grid.

usage: python soil_ebod.py <window> <datadir> -> soil.npz (per-pixel attributes, NaN = unmapped)
Raw polygons stay in scratch; only derived statistics are committed."""

import math
import os
import sys
import urllib.request

import mapbox_vector_tile
import numpy as np
from affine import Affine
from pyproj import Transformer
from rasterio.features import rasterize
from shapely.geometry import shape
from shapely.ops import transform as stransform

sys.path.insert(0, os.path.dirname(__file__))
from windows import WINDOWS  # noqa: E402

name, D = sys.argv[1], sys.argv[2]
W = WINDOWS[name]
Z = 15
# legend: bodenkarte.at/styles/<field>.json
FIELDS = ("ackerwert", "gruendigkeit", "nutzbare_feldkapazitaet", "wasserverhaeltnisse", "durchlaessigkeit", "humuswert", "nitratrueckhalt")


def tile_xy(lon, lat):
    n = 2 ** Z
    return int((lon + 180) / 360 * n), int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)


b = W["bbox"]
x0, y1 = tile_xy(b[0], b[1])
x1, y0 = tile_xy(b[2], b[3])
to_utm = Transformer.from_crs(4326, W["epsg"], always_xy=True)
s2 = np.load(f"{D}/{name}/s2_2019.npz", mmap_mode="r")
T = Affine(*s2["transform"])
H, Wd = np.load(f"{D}/{name}/pixel_lab.npy").shape
feats = {k: [] for k in FIELDS}
textures = []
n_poly = 0
for tx in range(x0, x1 + 1):
    for ty in range(y0, y1 + 1):
        raw = urllib.request.urlopen(f"https://bodenkarte.at/data/bodenkarte-tiles/{Z}/{tx}/{ty}.pbf", timeout=60).read()
        dec = mapbox_vector_tile.decode(raw)
        lay = dec.get("bodenform_mpoly")
        if not lay:
            continue
        ext = lay.get("extent", 4096)
        n = 2 ** Z

        def to_ll(x, y, tx=tx, ty=ty, ext=ext):
            lon = (tx + x / ext) / n * 360 - 180
            yy = ty + (1 - y / ext)  # tile y origin at bottom in decoded coords
            lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * yy / n))))
            return to_utm.transform(lon, lat)

        for f in lay["features"]:
            g = stransform(lambda xs, ys: tuple(zip(*[to_ll(a, c) for a, c in zip(np.atleast_1d(xs), np.atleast_1d(ys))])), shape(f["geometry"]))
            p = f["properties"]
            n_poly += 1
            for k in FIELDS:
                v = p.get(k)
                # class codes, higher = better (ackerwert 1-5, gruendigkeit 1-5, nFK 1-5);
                # 0 = "stark schwankend" / "uneinheitlich" (not ordinal) -> unmapped
                if v is not None and v > 0:
                    feats[k].append((g, float(v)))
            if p.get("bodenart"):
                textures.append((g, p["bodenart"]))
out = {}
for k, items in feats.items():
    a = rasterize(items, out_shape=(H, Wd), transform=T, fill=-9999, dtype="float32") if items else np.full((H, Wd), -9999, "f4")
    out[k] = np.where(a == -9999, np.nan, a).astype("f4")
codes = sorted({t for _, t in textures})
tex = rasterize([(g, codes.index(t) + 1) for g, t in textures], out_shape=(H, Wd), transform=T, fill=0, dtype="int16") if textures else np.zeros((H, Wd), "i2")
np.savez(f"{D}/{name}/soil.npz", texture=tex, texture_codes=np.array(codes), **out)
print(name, "tiles", (x1 - x0 + 1) * (y1 - y0 + 1), "polygons", n_poly, {k: round(float(np.isfinite(v).mean()), 2) for k, v in out.items()}, "textures", codes[:12])
