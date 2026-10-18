"""Daily weather per window, 1991-2025, plus per-season indicators and their 1991-2020 percentiles.

AT windows: GeoSphere Austria SPARTACUS v2 (1 km gridded daily RR/TN/TX, CC-BY 4.0) at the window centre.
Uckermark: DWD daily climate station 01869 Gruenow (2.8 km from the window centre; DWD open data,
CC-BY 4.0 / GeoNutzV). ET0 by Hargreaves-Samani. Open-Meteo hit its daily quota from this egress.

usage: python weather.py <window> <datadir> -> weather_daily.csv, results/<window>_weather.json"""

import io
import json
import os
import sys
import urllib.request
import zipfile

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from windows import WINDOWS  # noqa: E402

name, D = sys.argv[1], sys.argv[2]
W = WINDOWS[name]
b = W["bbox"]
lat, lon = (b[1] + b[3]) / 2, (b[0] + b[2]) / 2


def get(url):
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.read()


if W["cc"] == "at":
    parts = []
    for a, z in (("1991-01-01", "2007-12-31"), ("2008-01-01", "2025-12-31")):
        js = json.loads(get(f"https://dataset.api.hub.geosphere.at/v1/timeseries/historical/spartacus-v2-1d-1km?parameters=RR,TN,TX&start={a}&end={z}&lat_lon={lat:.4f},{lon:.4f}"))
        p = js["features"][0]["properties"]["parameters"]
        parts.append(pd.DataFrame({"date": pd.to_datetime([t[:10] for t in js["timestamps"]]), "rr": p["RR"]["data"], "tn": p["TN"]["data"], "tx": p["TX"]["data"]}))
    df = pd.concat(parts)
    source = f"GeoSphere Austria SPARTACUS v2 1 km daily at {lat:.3f}N {lon:.3f}E"
else:
    base = "https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/daily/kl/"
    frames = []
    for sub in ("historical/", "recent/"):
        listing = get(base + sub).decode("latin1")
        fn = [x for x in listing.split('"') if x.startswith("tageswerte_KL_01869") and x.endswith(".zip")][0]
        zf = zipfile.ZipFile(io.BytesIO(get(base + sub + fn)))
        prod = [n for n in zf.namelist() if n.startswith("produkt_")][0]
        f = pd.read_csv(zf.open(prod), sep=";", skipinitialspace=True)
        frames.append(pd.DataFrame({"date": pd.to_datetime(f.MESS_DATUM.astype(str)), "rr": f.RSK, "tn": f.TNK, "tx": f.TXK}))
    df = pd.concat(frames).drop_duplicates("date").replace(-999, np.nan)
    source = "DWD station 01869 Gruenow (daily KL)"
df = df[(df.date >= "1991-01-01") & (df.date <= "2025-12-31")].sort_values("date").reset_index(drop=True)
# Hargreaves ET0 (mm/day)
doy = df.date.dt.dayofyear.values
phi = np.radians(lat)
dr = 1 + 0.033 * np.cos(2 * np.pi * doy / 365)
dec = 0.409 * np.sin(2 * np.pi * doy / 365 - 1.39)
ws = np.arccos(-np.tan(phi) * np.tan(dec))
ra = 24 * 60 / np.pi * 0.082 * dr * (ws * np.sin(phi) * np.sin(dec) + np.cos(phi) * np.cos(dec) * np.sin(ws))
tm = (df.tn + df.tx) / 2
df["et0"] = 0.0023 * 0.408 * ra * (tm + 17.8) * np.sqrt((df.tx - df.tn).clip(lower=0))
df["gdd5"] = (tm - 5).clip(lower=0)
os.makedirs(f"{D}/{name}", exist_ok=True)
df.to_csv(f"{D}/{name}/weather_daily.csv", index=False)


def seg(y, a, z):
    s = df[(df.date >= f"{y}-{a}") & (df.date <= f"{y}-{z}")]
    return s


def longest_dry(s):
    run = best = 0
    for v in (s.rr.fillna(0) < 1).values:
        run = run + 1 if v else 0
        best = max(best, run)
    return best


rows = []
for y in range(1992, 2026):
    w_ = df[(df.date >= f"{y-1}-10-01") & (df.date <= f"{y}-03-31")]
    spr, summ = seg(y, "04-01", "06-30"), seg(y, "07-01", "09-30")
    aut = seg(y - 1, "09-01", "11-30")
    rows.append(dict(year=y, p_winter=w_.rr.sum(), p_autumn_prev=aut.rr.sum(), p_aprjun=spr.rr.sum(), cwb_aprjun=(spr.rr - spr.et0).sum(),
                     p_julsep=summ.rr.sum(), cwb_julsep=(summ.rr - summ.et0).sum(), gdd_marOct=seg(y, "03-01", "10-31").gdd5.sum(),
                     heat_days=int((seg(y, "06-01", "08-31").tx >= 30).sum()), dry_spell_aprjun=longest_dry(spr),
                     frost_marapr=int((seg(y, "03-01", "04-30").tn <= -5).sum())))
Y = pd.DataFrame(rows).set_index("year")
ref = Y.loc[1992:2020]
pct = {c: {int(y): round(float((ref[c] < Y.at[y, c]).mean()), 2) for y in range(2019, 2026)} for c in Y.columns}
R = dict(source=source, normal="1992-2020 (29 seasons)", years={int(y): {c: round(float(Y.at[y, c]), 1) for c in Y.columns} for y in range(2019, 2026)},
         normal_median={c: round(float(ref[c].median()), 1) for c in Y.columns}, percentile_vs_normal=pct)
json.dump(R, open(f"results/{name}_weather.json", "w"), indent=1)
print(name, source)
print(Y.loc[2019:2025].round(0).to_string())
print("normal median", R["normal_median"])
