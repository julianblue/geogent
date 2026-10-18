"""A8: does the preceding crop's harvest date (a proxy for late sowing) weaken winter cereals,
and is the effect larger after a wet winter? Motivated by tr-115077081 (barley 2024 after soy
harvested ~3 Oct, then the wettest winter since 1992).

Unit-years: winter cereal in year Y (2020+), the same unit declared and harvested in Y-1.
Outcome: z_peer of season greenness and of peak NDVI (crop x year x 5 km removed).
Preceding class: cereal (rotation effect, early harvest) | early non-cereal (harvest <= DOY 250)
| late row crop (harvest >= DOY 260). Bootstrap 95% CIs over units. Winter precipitation from
weather.py (Oct-Mar, year-level), so the interaction has n = years per window."""

import json
import sys

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

name, D = sys.argv[1], sys.argv[2]
F = pd.read_csv(f"{D}/{name}/features.csv")
Wx = json.load(open(f"results/{name}_weather.json"))
prev = F.set_index(["uid", "year"])
rows = []
for _, r in F[(F.group == "winter cereal") & (F.year >= 2020) & F.indvi_season_zpeer.notna()].iterrows():
    if (r.uid, r.year - 1) not in prev.index:
        continue
    p = prev.loc[(r.uid, r.year - 1)]
    if not isinstance(p.group, str) or pd.isna(p.harvest_doy):
        continue
    cls = "cereal" if p.group in ("winter cereal", "spring cereal") else ("late row crop" if p.harvest_doy >= 260 else ("early non-cereal" if p.harvest_doy <= 250 else None))
    if cls:
        rows.append(dict(uid=r.uid, year=r.year, cls=cls, prev=p.hcat, prev_harvest=p.harvest_doy, z=float(np.clip(r.indvi_season_zpeer, -5, 5)),
                         zpk=float(np.clip(r.peak_ndvi_zpeer, -5, 5)) if pd.notna(r.peak_ndvi_zpeer) else np.nan, crop=r.hcat))
A = pd.DataFrame(rows)
rng = np.random.default_rng(0)


def boot(v):
    v = np.asarray(v)
    m = [rng.choice(v, len(v)).mean() for _ in range(2000)]
    return [round(float(v.mean()), 3), round(float(np.percentile(m, 2.5)), 3), round(float(np.percentile(m, 97.5)), 3)]


R = dict(n=len(A), by_class={c: dict(n=int((A.cls == c).sum()), z_greenness=boot(A.z[A.cls == c]), z_peak=boot(A.zpk[(A.cls == c) & A.zpk.notna()]))
                              for c in ("cereal", "early non-cereal", "late row crop") if (A.cls == c).sum() >= 15})
late = A[A.cls == "late row crop"]
if len(late) >= 20:
    R["late_rowcrop_harvest_doy_vs_z"] = dict(n=len(late), spearman=round(float(spearmanr(late.prev_harvest, late.z).statistic), 3),
                                              p=float(spearmanr(late.prev_harvest, late.z).pvalue), harvest_doy_iqr=[float(late.prev_harvest.quantile(.25)), float(late.prev_harvest.quantile(.75))])
yr = []
for y, g in A.groupby("year"):
    e, l = g.z[g.cls == "early non-cereal"], g.z[g.cls == "late row crop"]
    if len(e) >= 8 and len(l) >= 8:
        yr.append(dict(year=int(y), p_winter=Wx["years"][str(y)]["p_winter"], p_winter_pct=Wx["percentile_vs_normal"]["p_winter"][str(y)], late_minus_early=round(float(l.mean() - e.mean()), 3), n_late=len(l), n_early=len(e)))
R["by_year"] = yr
if len(yr) >= 4:
    R["late_penalty_vs_winter_precip"] = dict(n_years=len(yr), spearman=round(float(spearmanr([x["p_winter"] for x in yr], [x["late_minus_early"] for x in yr]).statistic), 3))
R["top_preceding_late"] = late.prev.value_counts().head(4).to_dict()
json.dump(R, open(f"results/{name}_a8_preceding.json", "w"), indent=1)
print(name, json.dumps(R, indent=1))
