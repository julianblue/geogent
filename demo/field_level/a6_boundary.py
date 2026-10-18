"""A6 boundary and label quality.

(a) FTW PRUE predicted fields (2024/2025 determinations) vs same-year declared parcels:
    best IoU per declared parcel, splits (>=2 predictions each covering >=15% of a parcel),
    merges (a prediction holding >=50% of >=2 parcels), unregistered prediction area (<20%
    covered by any declared parcel). Interior only: centroids >=300 m inside the window.
    Link to field metrics: are split parcels internally more heterogeneous (TESSERA dispersion)?
(b) EuroCrops vs FTW harmonized for the same country-year: geometry IoU + HCAT label agreement."""

import json
import os
import sys

import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy.stats import mannwhitneyu
from shapely import STRtree, box, wkt

sys.path.insert(0, os.path.dirname(__file__))
from windows import WINDOWS  # noqa: E402

name, D = sys.argv[1], sys.argv[2]
W = WINDOWS[name]
P = json.load(open(f"{D}/{name}/parcels_utm.json"))
pred = json.load(open(f"{D}/{name}/predicted_utm.json"))
t = Transformer.from_crs(4326, W["epsg"], always_xy=True)
b = W["bbox"]
xs, ys = zip(*[t.transform(x, y) for x in b[0::2] for y in b[1::2]])
interior = box(max(min(xs), min(xs)) + 300, min(ys) + 300, max(xs) - 300, max(ys) - 300)
R = {}
for yr in ("2024", "2025", "2023"):
    if yr not in P:
        continue
    pg = [wkt.loads(p["wkt"]).buffer(0) for p in pred if p["when"].startswith(yr)]
    if not pg:
        continue
    dg = [wkt.loads(p["wkt"]).buffer(0) for p in P[yr]]
    keep = [i for i, g in enumerate(dg) if interior.contains(g.centroid) and g.area >= 5000]
    tp, td = STRtree(pg), STRtree(dg)
    best, split = [], []
    for i in keep:
        g = dg[i]
        ious, covers = [0.0], []
        for j in tp.query(g):
            inter = g.intersection(pg[j]).area
            ious.append(inter / g.union(pg[j]).area)
            if inter / g.area >= 0.15:
                covers.append(j)
        best.append(max(ious))
        split.append(len(covers) >= 2)
    merges, unreg_area, tot_area = 0, 0.0, 0.0
    for j, g in enumerate(pg):
        if not interior.contains(g.centroid):
            continue
        held = [i for i in td.query(g) if dg[i].intersection(g).area / dg[i].area >= 0.5]
        merges += len(held) >= 2
        cov = sum(dg[i].intersection(g).area for i in td.query(g))
        tot_area += g.area
        unreg_area += g.area if cov / g.area < 0.2 else 0
    best = np.array(best)
    declared_area = sum(dg[i].area for i in keep)
    covered = sum(dg[i].intersection(pg[j]).area for i in keep for j in tp.query(dg[i]))
    R[f"pred_vs_declared_{yr}"] = dict(n_declared=len(keep), n_pred=len(pg), iou_median=round(float(np.median(best)), 3),
                                       iou_ge_0_5=round(float((best >= 0.5).mean()), 3), iou_ge_0_7=round(float((best >= 0.7).mean()), 3),
                                       no_match=round(float((best < 0.1).mean()), 3), split_share=round(float(np.mean(split)), 3),
                                       merge_count=int(merges), unregistered_pred_area_share=round(unreg_area / max(tot_area, 1), 3),
                                       declared_area_covered_by_pred=round(covered / declared_area, 3))
    # link to field metrics via units (ref-year ids)
    if yr == str(max(int(k) for k in P)):
        F = pd.read_csv(f"{D}/{name}/features.csv")
        ids = {P[yr][i]["id"]: (s, bi) for i, s, bi in zip(keep, split, best)}
        f = F[(F.year == int(yr)) & F.tess_px.ge(20)].copy()
        f["pid"] = f.uid.str.split("-", n=1).str[1]
        f = f[f.pid.isin(ids)]
        f["split"] = [ids[p][0] for p in f.pid]
        f["iou"] = [ids[p][1] for p in f.pid]
        a, c = f.tess_disp[f.split], f.tess_disp[~f.split]
        R[f"split_vs_heterogeneity_{yr}"] = dict(n_split=len(a), n_other=len(c), median_disp_split=round(a.median(), 3), median_disp_other=round(c.median(), 3),
                                                 mannwhitney_p=float(mannwhitneyu(a, c).pvalue), spearman_iou_vs_ha=round(f[["iou", "ha"]].corr("spearman").iloc[0, 1], 3))
# (b) EuroCrops vs FTW
for f in os.listdir(f"{D}/{name}"):
    if not f.startswith("ec_"):
        continue
    yr = f[3:7]
    if yr not in P:
        continue
    ec = json.load(open(f"{D}/{name}/{f}"))
    eg = [wkt.loads(e["wkt"]).buffer(0) for e in ec]
    fg = [wkt.loads(p["wkt"]).buffer(0) for p in P[yr]]
    tr = STRtree(eg)
    iou, agree, agree_name = [], [], []
    for p, g in zip(P[yr], fg):
        bj, bi = None, 0.0
        for j in tr.query(g):
            v = g.intersection(eg[j]).area / g.union(eg[j]).area
            if v > bi:
                bj, bi = j, v
        iou.append(bi)
        if bj is not None and bi >= 0.5:
            agree.append(str(p["hcat_code"]) == ec[bj]["hcat_c"])
            agree_name.append((p["hcat"], ec[bj]["hcat_n"]))
    iou = np.array(iou)
    dis = pd.Series([a for a, ok in zip(agree_name, agree) if not ok]).value_counts().head(5)
    R[f"eurocrops_vs_ftw_{yr}"] = dict(n_ftw=len(fg), n_ec=len(eg), iou_median=round(float(np.median(iou)), 3), iou_ge_0_9=round(float((iou >= 0.9).mean()), 3),
                                       matched=len(agree), hcat_code_agreement=round(float(np.mean(agree)), 3) if agree else None,
                                       top_disagreements=[[list(k), int(v)] for k, v in dis.items()])
json.dump(R, open(f"results/{name}_a6_boundary.json", "w"), indent=1)
print(json.dumps(R, indent=1))
