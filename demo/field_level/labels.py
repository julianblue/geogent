"""Declared parcels (FTW harmonized, every year) + FTW model-predicted boundaries for a window.

usage: python labels.py <window> <outdir>  ->  <outdir>/<window>/parcels_utm.json, predicted_utm.json
       python labels.py <window> <outdir> 2015 2016 ...  ->  parcels_utm_hist.json (those years only)
Geometries are reprojected to the window's UTM; bbox pruning runs in each file's own CRS."""

import json
import os
import re
import sys

import duckdb
import numpy as np
import shapely
from pyproj import CRS, Transformer
from shapely import wkb

sys.path.insert(0, os.path.dirname(__file__))
from windows import FTW_YEARS, PRED_COUNTRY, WINDOWS  # noqa: E402

name, out = sys.argv[1], sys.argv[2]
HIST = [int(y) for y in sys.argv[3:]]
W = WINDOWS[name]
os.makedirs(f"{out}/{name}", exist_ok=True)
con = duckdb.connect()
con.execute("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial; SET enable_server_cert_verification=true; SET ca_cert_file='/root/.ccr/ca-bundle.crt'")
BASE = "https://data.source.coop/ftw"


def file_epsg(url):
    """File CRS: 'EPSG:n', 'OGC:CRS84', or inline PROJJSON (AT 2019/2020 files)."""
    t = [r[1] for r in con.execute(f"DESCRIBE SELECT geometry FROM '{url}'").fetchall()][0]
    m = re.search(r"EPSG:(\d+)'", t)
    if m:
        return int(m.group(1))
    if "CRS84" in t or t == "GEOMETRY":
        return 4326
    return CRS.from_json(t[t.index("'") + 1 : t.rindex("'")])


def fetch(url, cols, full_inside=True):
    epsg = file_epsg(url)
    t = Transformer.from_crs(4326, epsg, always_xy=True)
    b = W["bbox"]
    xs, ys = zip(*[t.transform(x, y) for x in b[0::2] for y in b[1::2]])
    cond = (f"bbox.xmin>={min(xs)} AND bbox.xmax<={max(xs)} AND bbox.ymin>={min(ys)} AND bbox.ymax<={max(ys)}" if full_inside
            else f"bbox.xmax>={min(xs)} AND bbox.xmin<={max(xs)} AND bbox.ymax>={min(ys)} AND bbox.ymin<={max(ys)}")
    rows = con.execute(f"SELECT {cols}, ST_AsWKB(geometry) FROM '{url}' WHERE {cond}").fetchall()
    to = Transformer.from_crs(epsg, W["epsg"], always_xy=True)
    return [(r[:-1], shapely.transform(wkb.loads(bytes(r[-1])), lambda c: np.column_stack(to.transform(c[:, 0], c[:, 1])))) for r in rows]


cc = W["cc"]
P = {}
for y in HIST or FTW_YEARS[cc]:
    rows = fetch(f"{BASE}/harmonized-field-data/{cc}/year={y}/{cc}-{y}.parquet", 'id, "crop:name", "hcat:name_en", "hcat:code"')
    P[y] = [dict(id=str(r[0]), crop=r[1], hcat=r[2], hcat_code=r[3], wkt=g.wkt, ha=g.area / 1e4) for r, g in rows if g.is_valid or g.buffer(0).is_valid]
    print(name, y, len(P[y]), "parcels", round(sum(f["ha"] for f in P[y])), "ha", flush=True)
json.dump(P, open(f"{out}/{name}/parcels_utm{'_hist' if HIST else ''}.json", "w"))
if HIST:
    sys.exit(0)

u = f"{BASE}/global-data/predictions/vectors/alpha/results-by-admin-conf/admin:country_code={PRED_COUNTRY[cc]}.parquet"
rows = fetch(u, 'id, confidence, "determination:datetime"')
pred = [dict(id=str(r[0]), conf=r[1], when=str(r[2]), wkt=g.wkt, ha=g.area / 1e4) for r, g in rows]
print(name, "predicted", len(pred), "fields; determination dates", sorted({p["when"][:10] for p in pred})[:5], flush=True)
json.dump(pred, open(f"{out}/{name}/predicted_utm.json", "w"))
