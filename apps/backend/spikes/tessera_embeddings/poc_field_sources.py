"""PoC: bbox-filtered field boundaries + crop labels from open GeoParquet.

Spike for the TESSERA-embeddings / deep-analysis work. NOT production code — no
FastAPI wiring, no caching, no registry. The point is to de-risk the "where do
field polygons and crop labels come from" question before we commit to it: prove
that for a small AOI we can pull

  (a) **declared** crop-field boundaries + crop-type labels (Austrian INVEKOS
      parcels, harmonized by Fields of the World into fiboa GeoParquet on Source
      Cooperative), and
  (b) **predicted** field boundaries without labels (FTW global, PRUE model on
      Sentinel-2, 2024 + 2025),

with *HTTP range reads only* (no whole-country downloads), and measure what that
costs (latency, requests, bytes). It then

  1. normalises both to one schema in EPSG:4326 and writes GeoParquet,
  2. reports crop-class counts, field-size and FTW-confidence distributions,
  3. checks how well FTW polygons reproduce the declared ones (IoU matching) —
     i.e. how usable FTW is where no declarations exist, and
  4. derives a draft HCAT -> "season regime" mapping (SEASON_REGIME_BY_HCAT).

How the bbox pruning works: both datasets are GeoParquet 1.1 with a per-feature
``bbox`` struct (xmin/ymin/xmax/ymax) covering column, and the rows are spatially
sorted, so the per-row-group min/max statistics of that column let the Parquet
reader skip most row groups. Filtering on ``bbox.xmin <= ... AND ...`` (in the
file's own CRS — EPSG:31287 for Austria, WGS84 for FTW) is therefore what makes
the query cheap; ``ST_Intersects`` alone would read every geometry.

Run (isolated venv, deps NOT added to the backend project; DuckDB >= 1.5 is
needed for the typed GEOMETRY column that carries the GeoParquet CRS):

    uv venv --python 3.12 /tmp/venv-fields
    uv pip install --python /tmp/venv-fields/bin/python \\
        duckdb pyarrow geopandas shapely pyproj
    /tmp/venv-fields/bin/python \\
        apps/backend/spikes/tessera_embeddings/poc_field_sources.py --out-dir /tmp/fields_out

Data is anonymous HTTPS on https://data.source.coop (no credentials). TLS
verification is explicitly switched ON (DuckDB's ``enable_server_cert_verification``
defaults to *false*); behind the sandbox proxy the proxy CA is picked up from the
system store, or from SSL_CERT_FILE / CURL_CA_BUNDLE via ``SET ca_cert_file``.

Licences (from each collection's ``collection.json`` / file metadata):
  * ftw/harmonized-field-data/at   CC-BY-4.0  (Agrarmarkt Austria; EuroCrops V2
    for 2015-2017). Attribution required.
  * ftw/global-data predictions    CC-BY-4.0  (Taylor Geospatial Institute +
    Microsoft AI for Good). Attribution required.
Other harmonized collections differ (CC0, CC-BY-SA, DL-DE-*, CC-BY-NC for
br_conab) — check ``collection.json`` before adding a country.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import duckdb
import geopandas as gpd
import numpy as np
import pandas as pd
import pyproj
import shapely

HARMONIZED_BASE = "https://data.source.coop/ftw/harmonized-field-data"
FTW_GLOBAL_BASE = (
    "https://data.source.coop/ftw/global-data/predictions/vectors/alpha/results-by-admin-conf"
)
# NB: the physical prefix is ``ftw/global-data/``; ``tge-labs/ftw-global-data/`` is 404.
FTW_AT_URL = f"{FTW_GLOBAL_BASE}/admin:country_code=AT/Austria.parquet"

# Marchfeld, Lower Austria (arable plain east of Vienna). lon/lat, EPSG:4326.
DEFAULT_AOI = (16.58, 48.24, 16.62, 48.27)  # west, south, east, north
FTW_RECOMMENDED_CONFIDENCE = 69  # README: "recommended default filter: confidence >= 69"

# --- Draft season regime ---------------------------------------------------------------------
# Season regime drives which Sentinel-2 / TESSERA time window is informative for a field:
#   winter_cereal        autumn-sown, green in spring, harvested ~July (also winter rapeseed/poppy
#                        — same phenology window)
#   spring_crop          sown Feb-Apr, harvested Jul-Aug (spring cereals, grain legumes, flax, ...)
#   summer_crop          sown Apr-Jun, peak Jul-Aug, harvested Sep-Oct (maize, soy, beet, potato,
#                        sunflower, pumpkin, sorghum/millet, pseudo-cereals)
#   grassland_permanent  perennial/forage cover all year (pasture, meadow, leys, lucerne, clover,
#                        turf) — no bare-soil phase
#   fallow               set-aside / green fallow (kept apart: it is "not cropped", not "unknown")
#   other                everything else, incl. horticulture/vegetables (multi-cropping, season
#                        ambiguous), permanent crops (orchard, vineyard), greenhouse, forest,
#                        unmaintained, unknown
# Keys are HCAT code *prefixes* (HCAT is hierarchical by digit prefix: 4/6/8/10 digits get more
# specific); the longest matching prefix wins. HCAT groups maize/millet etc. coarsely, so the
# mapping is by design a bit blunter than the source crop list.
SEASON_REGIME_BY_HCAT: dict[str, str] = {
    # -- winter_cereal (xxxx01 = winter variant of the cereal) --------------------------------
    "3301010101": "winter_cereal",  # winter common/soft wheat
    "3301010201": "winter_cereal",  # winter durum wheat
    "33010103": "winter_cereal",  # rye (unspecified -> winter; spring rye overridden below)
    "3301010301": "winter_cereal",  # winter rye
    "3301010401": "winter_cereal",  # winter barley
    "3301010501": "winter_cereal",  # winter oats
    "3301010801": "winter_cereal",  # winter triticale
    "3301011001": "winter_cereal",  # winter spelt
    "3301011101": "winter_cereal",  # winter meslin
    "3301011201": "winter_cereal",  # winter emmer / einkorn
    "3301060401": "winter_cereal",  # winter rapeseed (winter-sown oilseed)
    "3301060601": "winter_cereal",  # winter poppy
    # -- spring_crop --------------------------------------------------------------------------
    "3301010102": "spring_crop",  # spring common wheat
    "3301010202": "spring_crop",  # spring durum wheat
    "3301010302": "spring_crop",  # spring rye
    "3301010402": "spring_crop",  # spring barley
    "3301010502": "spring_crop",  # spring oats
    "3301010802": "spring_crop",  # spring triticale
    "3301011002": "spring_crop",  # spring spelt
    "3301011102": "spring_crop",  # spring meslin
    "3301011202": "spring_crop",  # spring emmer / einkorn
    "3301011400": "spring_crop",  # canary seed
    "330102": "spring_crop",  # grain legumes: beans, chickpeas, lentils, peas, lupins
    "3301060403": "spring_crop",  # summer (spring-sown) rapeseed
    "3301060602": "spring_crop",  # spring poppy
    "330106070": "spring_crop",  # flax / linseed
    "3301060800": "spring_crop",  # oilseed crops (generic)
    "3301061500": "spring_crop",  # camelina
    "3301210100": "spring_crop",  # mustard
    # -- summer_crop --------------------------------------------------------------------------
    "3301010600": "summer_crop",  # maize (grain, seed, sugar corn)
    "3301090400": "summer_crop",  # green silo maize
    "3301010900": "summer_crop",  # millet / sorghum
    "3301030000": "summer_crop",  # potatoes
    "3301060500": "summer_crop",  # sunflower
    "3301061000": "summer_crop",  # hemp
    "3301140100": "summer_crop",  # cucumber / pickle
    "3301140400": "summer_crop",  # pumpkin / squash / oil pumpkin
    "33011501": "summer_crop",  # amaranth
    "33011502": "summer_crop",  # buckwheat
    "33011503": "summer_crop",  # quinoa
    "3301160000": "summer_crop",  # soybeans
    "3301180000": "summer_crop",  # topinambur
    "3301190000": "summer_crop",  # sage / chia
    "33012902": "summer_crop",  # beetroot
    "33012904": "summer_crop",  # fodder beet
    "3301290700": "summer_crop",  # sugar beet
    # -- grassland_permanent ------------------------------------------------------------------
    "3302": "grassland_permanent",  # pasture / meadow / grassland
    "3301020300": "grassland_permanent",  # esparsette (perennial forage legume)
    "3301090100": "grassland_permanent",  # temporary grass / ley
    "33010902": "grassland_permanent",  # grasses incl. sod / turf
    "33010903": "grassland_permanent",  # lucerne / clover / vetches
    # -- fallow -------------------------------------------------------------------------------
    "3301110000": "fallow",  # fallow land (green fallow)
}
DEFAULT_REGIME = "other"
REGIME_ORDER = [
    "winter_cereal",
    "spring_crop",
    "summer_crop",
    "grassland_permanent",
    "fallow",
    "other",
]


def season_regime(hcat_code: str | None) -> str:
    """Longest-prefix lookup of a 10-digit HCAT code in SEASON_REGIME_BY_HCAT."""
    if not hcat_code:
        return DEFAULT_REGIME
    code = str(hcat_code)
    for n in range(len(code), 3, -1):
        hit = SEASON_REGIME_BY_HCAT.get(code[:n])
        if hit:
            return hit
    return DEFAULT_REGIME


# --- DuckDB plumbing -------------------------------------------------------------------------


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial; INSTALL httpfs; LOAD httpfs;")
    con.execute("SET TimeZone = 'UTC'")
    # DuckDB's default is enable_server_cert_verification=false — turn it on explicitly.
    con.execute("SET enable_server_cert_verification = true")
    ca = os.environ.get("SSL_CERT_FILE") or os.environ.get("CURL_CA_BUNDLE")
    if ca and Path(ca).is_file():
        con.execute("SET ca_cert_file = ?", [ca])
    # per-request HTTP log -> request count + bytes (DuckDB >= 1.4)
    with contextlib.suppress(duckdb.Error):
        con.execute("CALL enable_logging('HTTP')")
    return con


@dataclass
class Cost:
    label: str
    seconds: float
    gets: int | None
    mbytes: float | None
    rows: int = 0


@contextmanager
def metered(con: duckdb.DuckDBPyConnection, label: str, sink: list[Cost]):
    """Time a block and count the HTTP GETs / response bytes DuckDB issued inside it."""
    with contextlib.suppress(duckdb.Error):
        con.execute("CALL truncate_duckdb_logs()")
    t0 = time.perf_counter()
    cost = Cost(label, 0.0, None, None)
    try:
        yield cost
    finally:
        cost.seconds = time.perf_counter() - t0
        try:
            row = con.execute(
                "SELECT count(*), coalesce(sum(try_cast(response.headers['Content-Length']"
                " AS BIGINT)), 0) FROM duckdb_logs_parsed('HTTP') WHERE request.type = 'GET'"
            ).fetchone()
            cost.gets, cost.mbytes = int(row[0]), float(row[1]) / 1e6
        except duckdb.Error:
            pass
        sink.append(cost)


def read_geo_meta(con: duckdb.DuckDBPyConnection, url: str) -> dict:
    """Parse the GeoParquet ``geo`` and ``collection`` key-value metadata of a remote file."""
    out: dict[str, dict] = {}
    rows = con.execute(
        f"SELECT decode(key), decode(value) FROM parquet_kv_metadata('{url}')"
        " WHERE decode(key) IN ('geo', 'collection')"
    ).fetchall()
    for key, value in rows:
        out[key] = json.loads(value)
    return out


def file_crs(meta: dict) -> pyproj.CRS:
    geo = meta["geo"]
    col = geo["columns"][geo["primary_column"]]
    crs = col.get("crs")
    # GeoParquet: crs omitted => OGC:CRS84 (lon/lat WGS84)
    return pyproj.CRS.from_json_dict(crs) if crs else pyproj.CRS.from_user_input("OGC:CRS84")


def has_bbox_covering(meta: dict) -> bool:
    geo = meta["geo"]
    return "bbox" in geo["columns"][geo["primary_column"]].get("covering", {})


def row_group_plan(
    con: duckdb.DuckDBPyConnection, url: str, bounds: tuple[float, float, float, float]
) -> tuple[int, int, float, float]:
    """(row groups touched, total, MB touched [all cols], MB total) from bbox column stats."""
    w, s, e, n = bounds
    sql = f"""
    WITH rg AS (
      SELECT row_group_id,
        min(try_cast(stats_min AS DOUBLE)) FILTER (WHERE path_in_schema = 'bbox, xmin') AS xmin,
        max(try_cast(stats_max AS DOUBLE)) FILTER (WHERE path_in_schema = 'bbox, xmax') AS xmax,
        min(try_cast(stats_min AS DOUBLE)) FILTER (WHERE path_in_schema = 'bbox, ymin') AS ymin,
        max(try_cast(stats_max AS DOUBLE)) FILTER (WHERE path_in_schema = 'bbox, ymax') AS ymax,
        sum(total_compressed_size) AS size
      FROM parquet_metadata('{url}') GROUP BY 1)
    SELECT count(*) FILTER (WHERE xmin <= {e} AND xmax >= {w} AND ymin <= {n} AND ymax >= {s}),
           count(*),
           coalesce(sum(size) FILTER (WHERE xmin <= {e} AND xmax >= {w}
                                      AND ymin <= {n} AND ymax >= {s}), 0) / 1e6,
           sum(size) / 1e6
    FROM rg"""
    a, b, c, d = con.execute(sql).fetchone()
    return int(a), int(b), float(c), float(d)


def fetch_bbox(
    con: duckdb.DuckDBPyConnection,
    url: str,
    bounds_src: tuple[float, float, float, float],
    *,
    use_covering: bool = True,
) -> pd.DataFrame:
    """Rows whose bbox intersects ``bounds_src`` (file CRS), normalised column names."""
    names = {r[0] for r in con.execute(f"SELECT name FROM parquet_schema('{url}')").fetchall()}

    def col(name: str, expr: str | None = None) -> str:
        return (expr or f'"{name}"') if name in names else "NULL"

    w, s, e, n = bounds_src
    if use_covering:
        where = f"bbox.xmin <= {e} AND bbox.xmax >= {w} AND bbox.ymin <= {n} AND bbox.ymax >= {s}"
    else:  # naive baseline: no covering-column predicate -> must read every geometry
        where = f"ST_Intersects(geometry, ST_GeomFromText('{shapely.box(w, s, e, n).wkt}'))"
    sql = f"""
    SELECT CAST(id AS VARCHAR)                       AS field_id,
           CAST({col("crop:code")} AS VARCHAR)       AS crop_code,
           CAST({col("crop:name")} AS VARCHAR)       AS crop_name,
           CAST({col("hcat:code")} AS VARCHAR)       AS hcat_code,
           CAST({col("hcat:name")} AS VARCHAR)       AS hcat_name,
           CAST({col("metrics:area")} AS DOUBLE)     AS area_m2,
           CAST({col("confidence")} AS DOUBLE)       AS confidence,
           {col("determination:datetime", 'year("determination:datetime")')} AS obs_year,
           ST_AsWKB(geometry)                        AS wkb
    FROM read_parquet('{url}')
    WHERE {where}"""
    return con.execute(sql).df()


def to_gdf(
    df: pd.DataFrame,
    crs: pyproj.CRS,
    aoi: tuple[float, float, float, float],
    *,
    source: str,
    year: int,
) -> gpd.GeoDataFrame:
    """WKB rows in the file CRS -> EPSG:4326 GeoDataFrame, exact-clipped to the AOI box."""
    geom = shapely.from_wkb([bytes(b) for b in df["wkb"]])
    gdf = gpd.GeoDataFrame(df.drop(columns="wkb"), geometry=geom, crs=crs).to_crs(4326)
    gdf = gdf[gdf.intersects(shapely.box(*aoi))].copy()  # bbox cover is a superset; drop corners
    if gdf["area_m2"].isna().any():
        utm = gdf.estimate_utm_crs()
        gdf["area_m2"] = gdf["area_m2"].fillna(gdf.to_crs(utm).area)
    gdf["source"] = source
    gdf["year"] = year
    gdf["season_regime"] = [season_regime(c) for c in gdf["hcat_code"]]
    if not gdf["hcat_code"].notna().any():
        gdf["season_regime"] = None
    return gdf[
        [
            "field_id",
            "crop_code",
            "crop_name",
            "hcat_code",
            "hcat_name",
            "area_m2",
            "source",
            "year",
            "season_regime",
            "confidence",
            "obs_year",
            "geometry",
        ]
    ].reset_index(drop=True)


# --- reporting -------------------------------------------------------------------------------


def size_report(gdf: gpd.GeoDataFrame, title: str) -> None:
    ha = gdf["area_m2"] / 1e4
    bins = [0, 0.5, 1, 2, 5, 10, 1e9]
    labels = ["<0.5", "0.5-1", "1-2", "2-5", "5-10", ">10"]
    hist = pd.cut(ha, bins=bins, labels=labels).value_counts().reindex(labels)
    q = ha.quantile([0.1, 0.25, 0.5, 0.75, 0.9])
    print(f"  [{title}] n={len(gdf)} total={ha.sum():.0f} ha mean={ha.mean():.2f} ha")
    print("    ha quantiles p10/p25/p50/p75/p90: " + " / ".join(f"{v:.2f}" for v in q))
    print("    size classes (ha): " + ", ".join(f"{k}: {v}" for k, v in hist.items()))


def crop_report(gdf: gpd.GeoDataFrame) -> None:
    print("  crop classes (HCAT name, count, ha):")
    g = (
        gdf.assign(ha=gdf["area_m2"] / 1e4)
        .groupby(gdf["hcat_name"].fillna("<no hcat>"))
        .agg(n=("field_id", "count"), ha=("ha", "sum"))
        .sort_values("n", ascending=False)
    )
    for name, r in g.head(15).iterrows():
        print(f"    {name:<42} {int(r.n):>4}  {r.ha:>8.1f} ha")
    if len(g) > 15:
        print(f"    ... {len(g) - 15} more classes ({int(g.n.iloc[15:].sum())} fields)")
    print(
        "  source crop names (top 8): "
        + ", ".join(f"{k} ({v})" for k, v in gdf["crop_name"].value_counts().head(8).items())
    )
    print("  season regime (count / ha):")
    reg = (
        gdf.assign(ha=gdf["area_m2"] / 1e4)
        .groupby("season_regime")
        .agg(n=("field_id", "count"), ha=("ha", "sum"))
        .reindex(REGIME_ORDER)
        .fillna(0)
    )
    for name, r in reg.iterrows():
        print(f"    {name:<20} {int(r.n):>4}  {r.ha:>8.1f} ha")


def confidence_report(gdf: gpd.GeoDataFrame) -> None:
    c = gdf["confidence"]
    ok = c.dropna()
    if ok.empty:
        print("    confidence: all null")
        return
    q = ok.quantile([0.1, 0.25, 0.5, 0.75, 0.9])
    share = (ok >= FTW_RECOMMENDED_CONFIDENCE).mean()
    print(
        f"    confidence null={c.isna().sum()} p10/p25/p50/p75/p90: "
        + " / ".join(f"{v:.0f}" for v in q)
        + f"  share>={FTW_RECOMMENDED_CONFIDENCE}: {share:.0%}"
    )


def iou_match(
    declared: gpd.GeoDataFrame, predicted: gpd.GeoDataFrame, aoi: tuple[float, ...]
) -> dict[str, float]:
    """How well do FTW polygons reproduce the declared parcels? (metric CRS, UTM)

    Declared fields count if their centroid is inside the AOI (so fields cut by the AOI edge
    don't bias the result); candidate FTW polygons are all that touch them. Reported:

    * best-IoU match of every declared field (>0.5 is the headline number);
    * the reverse (FTW polygons that match some declared field);
    * coverage: declared fields mostly (>50% of their area) inside ONE FTW polygon — separates
      "FTW merged/split parcels" (low IoU, high coverage) from "FTW is just wrong";
    * label purity: area-weighted share of the dominant declared crop inside each FTW polygon —
      i.e. would one label per FTW polygon be agronomically meaningful?
    """
    utm = declared.estimate_utm_crs()
    d = declared.to_crs(utm)
    p = predicted.to_crs(utm)
    aoi_utm = gpd.GeoSeries([shapely.box(*aoi)], crs=4326).to_crs(utm).iloc[0]
    d_geom = shapely.make_valid(d.geometry.values)
    p_geom = shapely.make_valid(p.geometry.values)
    d_idx = np.flatnonzero(shapely.contains(aoi_utm, shapely.centroid(d_geom)))
    p_idx = np.flatnonzero(shapely.contains(aoi_utm, shapely.centroid(p_geom)))
    area_d = shapely.area(d_geom[d_idx])

    # declared -> FTW
    di, pi = shapely.STRtree(p_geom).query(d_geom[d_idx], predicate="intersects")
    di = d_idx[di]
    inter = shapely.area(shapely.intersection(d_geom[di], p_geom[pi]))
    union = shapely.area(d_geom[di]) + shapely.area(p_geom[pi]) - inter
    iou = np.divide(inter, union, out=np.zeros_like(inter), where=union > 0)
    best_iou = np.zeros(len(d_geom))
    np.maximum.at(best_iou, di, iou)
    best_d = best_iou[d_idx]
    best_cov = np.zeros(len(d_geom))
    np.maximum.at(best_cov, di, inter / shapely.area(d_geom[di]))
    cov_d = best_cov[d_idx]
    best_p = np.zeros(len(p_geom))
    np.maximum.at(best_p, pi, iou)
    best_p_in = best_p[p_idx]

    # FTW -> declared (label purity inside each FTW polygon)
    pj, dj = shapely.STRtree(d_geom).query(p_geom[p_idx], predicate="intersects")
    pj = p_idx[pj]
    a = shapely.area(shapely.intersection(p_geom[pj], d_geom[dj]))
    frame = pd.DataFrame(
        {
            "p": pj,
            "hcat": d["hcat_name"].fillna("?").to_numpy()[dj],
            "regime": d["season_regime"].fillna("?").to_numpy()[dj],
            "a": a,
            "d_area": shapely.area(d_geom[dj]),
        }
    )
    frame = frame[frame["a"] > 0]

    def purity(col: str) -> float:
        g = frame.groupby(["p", col])["a"].sum()
        return float(g.groupby("p").max().sum() / g.sum())

    # parcels per FTW polygon: those with >50% of their own area inside it
    n_decl_per_ftw = frame[frame["a"] > 0.5 * frame["d_area"]].groupby("p").size()
    ha = area_d / 1e4
    out = {
        "n_declared": float(len(d_idx)),
        "n_ftw": float(len(p_idx)),
        "declared_matched_iou50": float((best_d > 0.5).mean()),
        "declared_matched_iou50_area_weighted": float(area_d[best_d > 0.5].sum() / area_d.sum()),
        "declared_matched_iou30": float((best_d > 0.3).mean()),
        "median_best_iou": float(np.median(best_d)),
        "ftw_matched_iou50": float((best_p_in > 0.5).mean()) if len(best_p_in) else float("nan"),
        "declared_mostly_inside_one_ftw (>50% area)": float((cov_d > 0.5).mean()),
        "declared_mostly_inside_one_ftw_area_weighted": float(
            area_d[cov_d > 0.5].sum() / area_d.sum()
        ),
        "ftw_label_purity_hcat (area-weighted)": purity("hcat"),
        "ftw_label_purity_regime (area-weighted)": purity("regime"),
        "declared_parcels_per_ftw_polygon (median, >50% inside)": float(n_decl_per_ftw.median()),
    }
    for lo, hi, name in [
        (0, 0.5, "lt0.5ha"),
        (0.5, 2, "0.5-2ha"),
        (2, 10, "2-10ha"),
        (10, 1e9, "gt10ha"),
    ]:
        m = (ha >= lo) & (ha < hi)
        out[f"matched_iou50[{name}] (n={int(m.sum())})"] = (
            float((best_d[m] > 0.5).mean()) if m.any() else float("nan")
        )
    return out


# --- main ------------------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--bbox", type=float, nargs=4, default=DEFAULT_AOI,
                    metavar=("W", "S", "E", "N"), help="AOI in EPSG:4326 lon/lat")  # fmt: skip
    ap.add_argument("--declared-years", type=int, nargs="+", default=[2024, 2025],
                    help="harmonized AT editions (2015-2025; newest is 2025)")  # fmt: skip
    ap.add_argument("--ftw-years", type=int, nargs="+", default=[2024, 2025])
    ap.add_argument("--out-dir", type=Path, default=Path("fields_out"))
    ap.add_argument("--naive-baseline", action="store_true",
                    help="also run the FTW query WITHOUT the bbox covering predicate (reads "
                    "every geometry, ~100+ MB) to show what pruning saves")  # fmt: skip
    args = ap.parse_args()
    aoi = tuple(args.bbox)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    costs: list[Cost] = []
    con = connect()
    print(f"AOI (EPSG:4326) W,S,E,N = {aoi}")

    declared: dict[int, gpd.GeoDataFrame] = {}
    predicted: dict[int, gpd.GeoDataFrame] = {}

    # ---- (a) declared, harmonized AT ------------------------------------------------------
    for year in args.declared_years:
        url = f"{HARMONIZED_BASE}/at/year={year}/at-{year}.parquet"
        print(f"\n== declared AT {year}: {url}")
        with metered(con, f"declared {year}: footer+metadata", costs):
            meta = read_geo_meta(con, url)
            crs = file_crs(meta)
            bounds = pyproj.Transformer.from_crs(4326, crs, always_xy=True).transform_bounds(
                *aoi, densify_pts=21
            )
            touched, total, mb_touched, mb_total = row_group_plan(con, url, bounds)
        lic = meta.get("collection", {}).get("license")
        print(
            f"  CRS={crs.to_string()} license={lic} covering_bbox={has_bbox_covering(meta)} "
            f"row groups touched {touched}/{total} ({mb_touched:.0f}/{mb_total:.0f} MB, all cols)"
        )
        with metered(con, f"declared {year}: bbox query", costs) as cost:
            df = fetch_bbox(con, url, bounds)
            cost.rows = len(df)
        gdf = to_gdf(df, crs, aoi, source="ftw-harmonized/at", year=year)
        declared[year] = gdf
        out = args.out_dir / f"declared_{year}.parquet"
        gdf.to_parquet(out, index=False, write_covering_bbox=True)
        print(f"  -> {len(df)} bbox hits, {len(gdf)} intersect AOI; wrote {out}")

    # ---- (b) FTW global predictions -------------------------------------------------------
    print(f"\n== FTW global predictions AT: {FTW_AT_URL}")
    with metered(con, "ftw: footer+metadata", costs):
        meta = read_geo_meta(con, FTW_AT_URL)
        crs = file_crs(meta)
        bounds = pyproj.Transformer.from_crs(4326, crs, always_xy=True).transform_bounds(
            *aoi, densify_pts=21
        )
        touched, total, mb_touched, mb_total = row_group_plan(con, FTW_AT_URL, bounds)
    print(
        f"  CRS={crs.to_string()} (no crs in geo metadata => GeoParquet default OGC:CRS84) "
        f"license=CC-BY-4.0 covering_bbox={has_bbox_covering(meta)} "
        f"row groups touched {touched}/{total} ({mb_touched:.0f}/{mb_total:.0f} MB, all cols)"
    )
    with metered(con, "ftw: bbox query (2024+2025)", costs) as cost:
        df = fetch_bbox(con, FTW_AT_URL, bounds)
        cost.rows = len(df)
    print(f"  {len(df)} bbox hits; obs_year counts: {df['obs_year'].value_counts().to_dict()}")
    for year in args.ftw_years:
        sub = df[df["obs_year"] == year]
        if sub.empty:
            print(f"  (no FTW polygons for {year})")
            continue
        gdf = to_gdf(sub, crs, aoi, source="ftw-global/prue", year=year)
        predicted[year] = gdf
        out = args.out_dir / f"ftw_{year}.parquet"
        gdf.to_parquet(out, index=False, write_covering_bbox=True)
        print(f"  {year}: {len(gdf)} fields intersect AOI; wrote {out}")
    if args.naive_baseline:
        with metered(con, "ftw: NAIVE ST_Intersects only (no covering)", costs) as cost:
            cost.rows = len(fetch_bbox(con, FTW_AT_URL, aoi, use_covering=False))

    # ---- distributions --------------------------------------------------------------------
    print("\n== AOI contents")
    for year, gdf in declared.items():
        print(f"\n declared {year}")
        crop_report(gdf)
        size_report(gdf, f"declared {year}")
    for year, gdf in predicted.items():
        print(f"\n FTW {year}")
        size_report(gdf, f"ftw {year}")
        confidence_report(gdf)
        hi = gdf[gdf["confidence"] >= FTW_RECOMMENDED_CONFIDENCE]
        print(f"    kept at confidence >= {FTW_RECOMMENDED_CONFIDENCE}: {len(hi)}/{len(gdf)}")

    # ---- FTW vs declared ------------------------------------------------------------------
    print("\n== FTW polygons vs declared (best-IoU match of each declared field)")
    for year in sorted(set(declared) & set(predicted)):
        res = iou_match(declared[year], predicted[year], aoi)
        print(f"\n year {year}: declared n={int(res['n_declared'])}, FTW n={int(res['n_ftw'])}")
        for k, v in res.items():
            if not k.startswith("n_"):
                print(f"    {k:<48} {v:.3f}")
        hi = predicted[year][predicted[year]["confidence"] >= FTW_RECOMMENDED_CONFIDENCE]
        if len(hi) and len(hi) < len(predicted[year]):
            r2 = iou_match(declared[year], hi, aoi)
            print(f"    [confidence>={FTW_RECOMMENDED_CONFIDENCE} only] declared matched "
                  f"IoU>0.5: {r2['declared_matched_iou50']:.3f}")  # fmt: skip
    if not (set(declared) & set(predicted)):
        print("  (no overlapping years between declared and FTW; nothing to compare)")

    # ---- cost table -----------------------------------------------------------------------
    print("\n== cost (HTTP range reads; anonymous https://data.source.coop)")
    print(f"  {'step':<44}{'sec':>7}{'GETs':>6}{'MB':>9}{'rows':>7}")
    for c in costs:
        gets = "-" if c.gets is None else str(c.gets)
        mb = "-" if c.mbytes is None else f"{c.mbytes:.1f}"
        print(f"  {c.label:<44}{c.seconds:>7.1f}{gets:>6}{mb:>9}{c.rows:>7}")


if __name__ == "__main__":
    main()
