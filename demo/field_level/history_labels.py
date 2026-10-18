"""Track older declarations (parcels_utm_hist.json from `labels.py <w> <d> 2015 2016 2017 2018`)
onto the units with units.py's rule (parcel covering >=80% of the unit), for an 11-year history.
Kept out of units.json so the 2019+ S2 pipeline is unchanged.
usage: python history_labels.py <window> <datadir> -> units_history.json {uid: {year: {...}|None}}"""

import json
import sys

from shapely import STRtree, wkt

name, D = sys.argv[1], sys.argv[2]
U = json.load(open(f"{D}/{name}/units.json"))["units"]
P = json.load(open(f"{D}/{name}/parcels_utm_hist.json"))
ug = [wkt.loads(u["wkt"]) for u in U]
H = {u["uid"]: {} for u in U}
for y, feats in P.items():
    g = [wkt.loads(f["wkt"]).buffer(0) for f in feats]
    tree = STRtree(g)
    for u, geom in zip(U, ug):
        best = (0.0, None)
        for j in tree.query(geom):
            ov = g[j].intersection(geom).area / geom.area
            if ov > best[0]:
                best = (ov, j)
        f = feats[best[1]] if best[0] >= 0.8 else None
        H[u["uid"]][y] = None if f is None else dict(crop=f["crop"], hcat=f["hcat"], hcat_code=f["hcat_code"])
json.dump(H, open(f"{D}/{name}/units_history.json", "w"))
print(name, {y: sum(H[u][y] is not None for u in H) for y in P}, "of", len(U))
