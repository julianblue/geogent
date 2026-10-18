"""Build field dossiers (dossier.schema.json) from the per-window tables.

usage: python dossier.py <window> <datadir> <uid> [<uid> ...] -> dossiers/<uid>.json
       python dossier.py <window> <datadir> --pick N   (auto-pick informative fields)"""

import json
import os
import sys

import numpy as np
import pandas as pd
from pyproj import Transformer
from shapely import wkt

sys.path.insert(0, os.path.dirname(__file__))
from common import ARABLE  # noqa: E402
from windows import WINDOWS  # noqa: E402

name, D = sys.argv[1], sys.argv[2]
W = WINDOWS[name]
F = pd.read_csv(f"{D}/{name}/anomaly.csv")
U = {u["uid"]: u for u in json.load(open(f"{D}/{name}/units.json"))["units"]}
PROF = pd.read_csv(f"{D}/{name}/rotation_profiles.csv").set_index("uid")
Z = pd.read_csv(f"{D}/{name}/zones.csv").set_index("uid")
ZM = np.load(f"{D}/{name}/zone_maps.npz")
lab = np.load(f"{D}/{name}/pixel_lab.npy")
inside_idx = np.flatnonzero(lab.ravel() > 0)
Wd = lab.shape[1]
to_ll = Transformer.from_crs(W["epsg"], 4326, always_xy=True)
EVID = {"history": "A1 (rotation AUC, LOYO group acc)", "management": "A2 (harvest vs calendar, cycles vs multi-crop, winter-cover persistence)",
        "performance": "A3 (peer percentile; field-effect ICC, crop-change caveat)", "within_field": "A4 (zone stability, edge control, binomial null, DEM rotated null)",
        "anomalies": "A5 (blinded curve review; in-season score)", "boundary": "A6 (PRUE vs declared)"}


def r(x, k=3):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else (round(float(x), k) if isinstance(x, (float, np.floating)) else x)


def direction(ui, cx, cy):
    key = f"u{ui}"
    if key not in ZM:
        return None
    px, _, low = ZM[key]
    low = low.astype(bool)
    if low.sum() < 5:
        return None
    rr, cc = np.divmod(inside_idx[px.astype(int)], Wd)
    dy, dx = -(rr[low].mean() - rr.mean()), cc[low].mean() - cc.mean()
    spread = np.hypot(rr - rr.mean(), cc - cc.mean()).mean()
    if np.hypot(dx, dy) < 0.25 * spread:
        return "scattered / central"
    ang = (np.degrees(np.arctan2(dx, dy)) + 360) % 360
    return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][int((ang + 22.5) // 45) % 8]


PRED = json.load(open(f"{D}/{name}/predicted_utm.json"))
PG = {}
for p in PRED:
    PG.setdefault(p["when"][:4], []).append(wkt.loads(p["wkt"]).buffer(0))


def boundary(u):
    """Best IoU of the unit vs FTW PRUE predicted fields (latest prediction year), and how many
    predictions cover >=15% of it (split) / whether the best prediction also holds other parcels (merge)."""
    yr = max(PG)
    g = wkt.loads(u["wkt"]).buffer(0)
    best, cov, bj = 0.0, 0, None
    for p in PG[yr]:
        if not p.intersects(g):
            continue
        inter = p.intersection(g).area
        iou = inter / p.union(g).area
        cov += inter / g.area >= 0.15
        if iou > best:
            best, bj = iou, p
    return dict(pred_year=int(yr), pred_best_iou=round(best, 3), pred_split=bool(cov >= 2),
                pred_block_ratio=None if bj is None else round(bj.area / g.area, 2),
                note="PRUE delineates field blocks; low IoU with ratio >1.5 = merged with neighbours (A6), not a data error")


def build(uid):
    g = F[F.uid == uid].sort_values("year")
    u = U[uid]
    c = wkt.loads(u["wkt"]).centroid
    lon, lat = to_ll.transform(c.x, c.y)
    nxt = g.set_index("year")
    hist, mgmt, perf, anom = [], [], [], []
    for _, x in g.iterrows():
        flags = []
        if x.tracked and pd.notna(x.p_declared_group) and x.p_declared_group < 0.05:
            flags.append(f"declaration looks like {x.emb_group}")
        if pd.notna(x.declared_change) and pd.notna(x.emb_yoy_centred) and (x.emb_yoy_centred >= 0.5) != bool(x.declared_change):
            flags.append("declared vs phenology change disagree")
        hist.append(dict(year=int(x.year), declared=x.hcat if x.tracked else None, group=x.group if x.tracked else None, embedding_group=x.emb_group if isinstance(x.emb_group, str) else None,
                         p_declared_group=r(x.p_declared_group), yoy_centred_distance=r(x.emb_yoy_centred),
                         phenology_change=None if pd.isna(x.emb_yoy_centred) else bool(x.emb_yoy_centred >= 0.5),
                         declared_change=None if pd.isna(x.declared_change) else bool(x.declared_change), flags=flags))
        if pd.isna(x.peak_ndvi):
            continue
        harvested = x.group in ARABLE and pd.notna(x.harvest_doy) and x.harvest_doy <= 250 and x.peak_ndvi >= 0.6
        wc = ("green" if x.winter_late >= 0.5 else "bare" if x.winter_late < 0.3 else "ambiguous") if harvested else "n/a"
        kind = None
        if wc == "green" and (x.year + 1) in nxt.index and isinstance(nxt.at[x.year + 1, "hcat"], str):
            kind = "autumn-sown next crop" if "WINTER" in nxt.at[x.year + 1, "hcat"].upper() else "cover/catch"
        mgmt.append(dict(year=int(x.year), sos_doy=r(x.sos), peak_doy=r(x.peak_doy), harvest_doy=r(x.harvest_doy), season_len_d=r(x.season_len),
                         n_cycles=r(x.n_cycles), winter_cover=wc, winter_green_kind=kind, bare_soil_days=r(x.bare_days)))
        if x.tracked and x.n_peers >= 5:
            perf.append(dict(year=int(x.year), crop=x.hcat, indvi_season=r(x.indvi_season, 1), pct_vs_peers=r(x.indvi_season_pct, 2), z_peer=r(x.indvi_season_zpeer, 2),
                             peak_ndvi_pct=r(x.peak_ndvi_pct, 2), peak_timing_vs_peers_z=r(x.peak_doy_zpeer, 2), n_peers=int(x.n_peers)))
        ev = [k[3:] for k in ("ev_low_peak", "ev_delayed_resown", "ev_no_harvest") if x[k] is True or x[k] == "True"]
        if (pd.notna(x.traj_dev_season) and x.traj_dev_season >= 4) or ev:
            anom.append(dict(year=int(x.year), traj_dev_season_z=r(x.traj_dev_season, 2), emb_dev_z=r(x.emb_dev, 2), events=ev))
    pr = PROF.loc[uid] if uid in PROF.index else None
    rot = None if pr is None else dict(n_years=int(pr.n_years), cereal_share=r(pr.cereal_share, 2), n_crops=int(pr.n_crops), group_entropy_bits=r(pr.group_entropy, 2),
                                       max_monoculture_run=int(pr.max_monoculture_run), declared_changes=int(pr.declared_changes), embedding_changes=int(pr.emb_changes),
                                       disagreements=int(pr.disagreements), percentile_in_window={"cereal_share": r((PROF.cereal_share < pr.cereal_share).mean(), 2),
                                                                                                   "group_entropy": r((PROF.group_entropy < pr.group_entropy).mean(), 2)})
    pcts = [p["pct_vs_peers"] for p in perf if p["pct_vs_peers"] is not None]
    psum = dict(n_years=len(pcts), mean_pct=r(np.mean(pcts), 2) if pcts else None, years_bottom_quartile=sum(p < 0.25 for p in pcts), years_top_quartile=sum(p > 0.75 for p in pcts),
                caveat="field effect is weak (A3 ICC ~0.1) and does not carry across crop changes; read single-year percentiles as season outcomes")
    wf = None
    if uid in Z.index:
        z = Z.loc[uid]
        wf = dict(n_px=int(z.n_px), n_years=int(z.n_years), stability_rho=r(z.stability), split_half_rho=r(z.split_half), persistent_low_frac=r(z.persistent_low_frac),
                  persistent_low_expected_by_chance=r(z.persistent_low_expected, 4), low_zone_direction=direction(int(z.ui), c.x, c.y),
                  terrain=None if "rho_dem" not in z else dict(rho_elevation=r(z.rho_dem), rho_twi=r(z.rho_twi), rho_elevation_rotated_null=r(z.rho_dem_null), relief_m=r(z.relief_m, 1)))
    d = dict(field=dict(uid=uid, window=name, area_ha=round(u["ha"], 2), centroid_lonlat=[round(lon, 5), round(lat, 5)], ref_year=int(g.year.max())),
             coverage=dict(years=[int(y) for y in g.year], declared_years=int(g.tracked.sum()), s2_clear_obs_per_year={int(a): r(b) for a, b in zip(g.year, g.n_obs)}, tessera_px=int(g.tess_px.max())),
             history=hist, rotation_profile=rot, management=mgmt, performance=dict(by_year=perf, summary=psum), within_field=wf, anomalies=anom,
             boundary=boundary(u), maci={"status": "PLACEHOLDER: 'MACI time series' undefined; awaiting Julian"}, evidence=EVID)
    d["narrative"] = narrative(d)
    return d


def narrative(d):
    s = []
    h = [x for x in d["history"] if x["declared"]]
    if h:
        s.append("Declared " + " -> ".join(f"{x['year']} {x['declared'].lower()}" for x in h) + ".")
    gaps = [x for x in d["history"] if not x["declared"] and x["embedding_group"]]
    if gaps:
        s.append("Untracked years inferred from embeddings (LOYO group acc ~0.9): " + ", ".join(f"{x['year']} ~{x['embedding_group']}" for x in gaps) + ".")
    rp = d["rotation_profile"]
    if rp:
        s.append(f"{rp['n_crops']} crops in {rp['n_years']} declared years, cereal share {rp['cereal_share']:.0%}, longest same-crop run {rp['max_monoculture_run']}y; "
                 f"{rp['disagreements']} declared-vs-phenology disagreement(s).")
    wc = [m for m in d["management"] if m["winter_cover"] in ("green", "bare")]
    if wc:
        g = [m for m in wc if m["winter_cover"] == "green"]
        s.append(f"After summer harvest the field was green over winter in {len(g)}/{len(wc)} seasons" + (" (" + ", ".join(f"{m['year']} {m['winter_green_kind'] or 'next crop not declared'}" for m in g) + ")" if g else "") + ".")
    hv = [m["harvest_doy"] for m in d["management"] if m["harvest_doy"]]
    p = d["performance"]["summary"]
    if p["n_years"]:
        s.append(f"Season greenness vs same-crop peers within 5 km: mean percentile {p['mean_pct']:.2f} over {p['n_years']} years "
                 f"({p['years_bottom_quartile']} bottom-quartile, {p['years_top_quartile']} top-quartile); weak persistence (A3), treat as season outcomes.")
    w = d["within_field"]
    if w:
        rel = "a stable pattern" if w["stability_rho"] >= 0.3 else "a weakly repeating pattern"
        s.append(f"Within-field: {rel} (year-to-year rho {w['stability_rho']:.2f}, {w['n_years']} seasons); {w['persistent_low_frac']:.0%} of the field is low-vigour in >=60% of seasons "
                 f"(chance {w['persistent_low_expected_by_chance']:.1%})" + (f", concentrated {w['low_zone_direction']}" if w["low_zone_direction"] and w["low_zone_direction"] != "scattered / central" else "") + ".")
        t = w.get("terrain")
        if t and abs(t["rho_elevation"]) >= 0.3 and abs(t["rho_elevation"]) > abs(t["rho_elevation_rotated_null"]) + 0.15:
            s.append(f"Vigour {'falls' if t['rho_elevation'] > 0 else 'rises'} toward lower ground (rho {t['rho_elevation']:.2f} vs rotated-DEM null {t['rho_elevation_rotated_null']:.2f}, relief {t['relief_m']} m).")
    a = [x for x in d["anomalies"] if x["events"] or (x["traj_dev_season_z"] or 0) >= 4]
    if a:
        s.append("Screen flags (unverified, ~27% in-season precision outside vegetables): " + "; ".join(f"{x['year']} " + (", ".join(x["events"]) or "off-peer trajectory") for x in a) + ".")
    return " ".join(s)


if sys.argv[3] == "--pick":
    n = int(sys.argv[4])
    z = Z[Z.n_years >= 5].copy()
    cand = z.sort_values("persistent_low_frac", ascending=False).index[:3].tolist()
    an = F[(F.traj_dev_season >= 4) & F.group.isin(ARABLE) & ~F.hcat.str.contains("VEGETABLES", na=False)].uid.value_counts()
    cand += an.index[:2].tolist()
    uids = list(dict.fromkeys(cand))[:n]
else:
    uids = sys.argv[3:]
os.makedirs("dossiers", exist_ok=True)
for uid in uids:
    d = build(uid)
    json.dump(d, open(f"dossiers/{uid}.json", "w"), indent=1, default=str)
    print(uid, "->", d["narrative"][:3000], "\n")
