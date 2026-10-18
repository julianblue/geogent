"""Field units = the latest declared year's parcels, tracked back through every year.

A unit's crop in year Y is the declared parcel covering >=80% of the unit (else None: split,
merge, or not declared). usage: python units.py <window> <datadir> -> units.json"""

import json
import os
import sys

from shapely import STRtree, wkt

sys.path.insert(0, os.path.dirname(__file__))
from windows import FTW_YEARS, WINDOWS  # noqa: E402

name, D = sys.argv[1], sys.argv[2]
years = FTW_YEARS[WINDOWS[name]["cc"]]
P = json.load(open(f"{D}/{name}/parcels_utm.json"))
ref = years[-1]
U = [dict(uid=f"{name[:2]}-{f['id'].removesuffix('.0')}", wkt=f["wkt"], ha=f["ha"]) for f in P[str(ref)] if f["ha"] >= 0.5]
ug = [wkt.loads(u["wkt"]) for u in U]
for y in years:
    g = [wkt.loads(f["wkt"]).buffer(0) for f in P[str(y)]]
    tree = STRtree(g)
    for u, geom in zip(U, ug):
        best = (0.0, None)
        for j in tree.query(geom):
            ov = g[j].intersection(geom).area / geom.area
            if ov > best[0]:
                best = (ov, j)
        f = P[str(y)][best[1]] if best[0] >= 0.8 else None
        u.setdefault("years", {})[y] = None if f is None else dict(id=f["id"], crop=f["crop"], hcat=f["hcat"], hcat_code=f["hcat_code"], cover=round(best[0], 3))
cov = {y: sum(u["years"][y] is not None for u in U) for y in years}
print(name, len(U), "units (ref year", ref, ") tracked per year:", cov)
json.dump(dict(ref_year=ref, years=years, units=U), open(f"{D}/{name}/units.json", "w"))
