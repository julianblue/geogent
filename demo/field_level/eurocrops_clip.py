"""Clip a EuroCrops shapefile (Zenodo 10118572, CC-BY-SA-4.0) to a window, reproject to UTM.

usage: python eurocrops_clip.py <window> <shp> <year> <datadir> -> ec_<year>.json"""

import json
import os
import sys

import numpy as np
import pyogrio
import shapely
from pyproj import CRS, Transformer

sys.path.insert(0, os.path.dirname(__file__))
from windows import WINDOWS  # noqa: E402

name, shp, year, D = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
W = WINDOWS[name]
crs = CRS.from_user_input(pyogrio.read_info(shp)["crs"])
t = Transformer.from_crs(4326, crs, always_xy=True)
b = W["bbox"]
xs, ys = zip(*[t.transform(x, y) for x in b[0::2] for y in b[1::2]])
meta, geoms = pyogrio.read_dataframe(shp, bbox=(min(xs), min(ys), max(xs), max(ys)), columns=["EC_hcat_n", "EC_hcat_c", "EC_trans_n"]).pipe(lambda df: (df.drop(columns="geometry"), df.geometry.values))
to = Transformer.from_crs(crs, W["epsg"], always_xy=True)
out = []
for (_, r), g in zip(meta.iterrows(), geoms):
    gx, gy, gX, gY = g.bounds
    if gx < min(xs) or gX > max(xs) or gy < min(ys) or gY > max(ys):
        continue
    g = shapely.transform(g, lambda c: np.column_stack(to.transform(c[:, 0], c[:, 1])))
    out.append(dict(hcat_n=r.EC_hcat_n, hcat_c=str(r.EC_hcat_c), trans=r.EC_trans_n, wkt=g.wkt, ha=g.area / 1e4))
json.dump(out, open(f"{D}/{name}/ec_{year}.json", "w"))
print(name, year, len(out), "EuroCrops parcels")
