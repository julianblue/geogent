"""Brandenburg soil-survey pits (Bodenschaetzung Grabloecher, LBGR WFS-BOGRABLOECHER; free of
charge, attribution LBGR) for a window -> soil_pits.csv in the window's UTM.

Per pit: wertzahlen (Bodenzahl/Ackerzahl, 7-100 soil quality), bodenart (texture class),
zustandsstufe (1 best - 7 worst development), entstehung, wasserstufe, freies_wasser (dm).
usage: python soil_bb.py <window> <datadir> <gml from GetFeature typeNames=app:gl_o_sch&bbox=...>"""

import os
import re
import sys

import pandas as pd
from pyproj import Transformer

sys.path.insert(0, os.path.dirname(__file__))
from windows import WINDOWS  # noqa: E402

name, D, gml = sys.argv[1], sys.argv[2], sys.argv[3]
W = WINDOWS[name]
txt = open(gml, encoding="utf-8").read()
to = Transformer.from_crs(25833, W["epsg"], always_xy=True)
rows = []
for m in re.findall(r"<app:gl_o_sch .*?</app:gl_o_sch>", txt, re.S):
    def g(tag):
        r = re.search(rf"<app:{tag}>(.*?)</app:{tag}>", m)
        return r.group(1) if r else None
    x, y = map(float, re.search(r"<gml:pos>(\S+) (\S+)</gml:pos>", m).groups())
    ux, uy = to.transform(x, y)
    rows.append(dict(id=g("id_nr"), x=ux, y=uy, date=g("datum"), deleted=g("geloescht"), old=g("altdaten"), kultur=g("kulturart"), bodenart=g("bodenart"),
                     zustand=g("zustandsstufe"), entstehung=g("entstehung"), wasserstufe=g("wasserstufe"), freies_wasser=g("freies_wasser"),
                     wertzahl=g("wertzahlen"), klassenflaeche=g("klassenflaechen")))
P = pd.DataFrame(rows)
P = P[(P.deleted != "1")]
for c in ("wertzahl", "zustand", "freies_wasser"):
    P[c] = pd.to_numeric(P[c], errors="coerce")
P.to_csv(f"{D}/{name}/soil_pits.csv", index=False)
print(name, len(P), "pits;", P.kultur.value_counts().to_dict(), "| wertzahl", P.wertzahl.describe()[["count", "min", "50%", "max"]].to_dict(), "| bodenart", P.bodenart.value_counts().head(8).to_dict())
