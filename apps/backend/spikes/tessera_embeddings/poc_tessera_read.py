"""PoC: read TESSERA yearly embeddings for a small AOI from AWS Open Data.

Spike for the TESSERA embeddings work (see docs/adr/0003-...). NOT production code — no
FastAPI wiring, no auth, no caching layer, no zone-seam stitching. The point is to de-risk the
read path before we commit to it: prove that we can

  1. open the global Icechunk (Zarr v3) store anonymously from AWS Open Data,
  2. slice one UTM-zone group down to a field-sized AOI (never the 66 TiB array!) for several
     years, dequantise (``embeddings * scales``) and read the QC arrays,
  3. characterise the data (schema, year convention, NaN/inf, observation counts, month
     coverage), and measure what a read costs (latency cold vs. warm, bytes on the wire),
  4. derive two cheap products a downstream step would use: per-pixel year-over-year cosine
     distance and a PCA(3) false-colour GeoTIFF.

It exposes ``read_embeddings(bbox_wgs84, years)`` so a follow-up step (per-field means) can
import it instead of re-implementing the windowing.

Store facts this relies on (verified live, see the printed schema):

  * bucket ``tessera-embeddings``, prefix ``v1.1/dclimate.icechunk``, us-west-2, anonymous;
    group per UTM zone+hemisphere (``33N``), dims (time, northing, easting, band);
  * ``spatial:transform`` is an affine with a PIXEL-CORNER origin, 10 m, north-up (northing
    descends), and ``time`` is the calendar year (``time_bnds`` = [Jan 1, Jan 1 next year));
  * ``scales`` (float32, PCodec) is NaN where a pixel was not embedded.

Run (isolated venv, deps NOT added to the backend project; Rust-based icechunk honours
SSL_CERT_FILE, which is pre-set in the agent sandbox — no extra proxy env needed):

    uv venv --python 3.12 /tmp/venv-tessera
    uv pip install --python /tmp/venv-tessera/bin/python \
        icechunk xarray zarr "numcodecs[pcodec]" numpy pyproj rasterio shapely
    /tmp/venv-tessera/bin/python apps/backend/spikes/tessera_embeddings/poc_tessera_read.py \
        --out-dir /tmp/tessera_out

Only the AOI's chunks are fetched (256x256x128 int8 inner chunks inside 2048x2048 shards);
a single pixel-year costs ~8.65 MB on the wire, so keep AOIs small and read in windows.
"""

from __future__ import annotations

import argparse
import math
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import icechunk
import numpy as np
import rasterio
import xarray as xr
from pyproj import Transformer
from rasterio.crs import CRS
from rasterio.transform import Affine

BUCKET = "tessera-embeddings"
PREFIX = "v1.1/dclimate.icechunk"
REGION = "us-west-2"
INNER_CHUNK = 256  # pixels; the unit of a fetch
DEFAULT_BBOX = (16.58, 48.24, 16.62, 48.27)  # Marchfeld, Lower Austria (lon/lat)
DEFAULT_YEARS = (2021, 2022, 2023, 2024, 2025)
QC_COUNTS = ("s2_obs_count", "s1_asc_obs_count", "s1_desc_obs_count")
QC_MONTHS = ("s2_month_covered", "s1_asc_month_covered", "s1_desc_month_covered")

BBox = tuple[float, float, float, float]


# --------------------------------------------------------------------------- store access


def open_repo() -> icechunk.Repository:
    """Open the public repo. Pass NO config object: the store ships reader-tuned settings."""
    storage = icechunk.s3_storage(bucket=BUCKET, prefix=PREFIX, region=REGION, anonymous=True)
    return icechunk.Repository.open(storage)


def open_group(group: str, repo: icechunk.Repository | None = None) -> xr.Dataset:
    """Lazy xarray view of one zone group. ``chunks=None`` => no dask graph over 8.7M chunks.

    Without dask there is no lazy wrapper protecting you: always ``isel`` before ``.values``.
    """
    repo = repo or open_repo()
    session = repo.readonly_session(branch="main")
    return xr.open_zarr(
        session.store, group=group, consolidated=False, decode_coords="all", chunks=None
    )


def zone_group_for(lon: float, lat: float) -> str:
    """Nominal 6-degree UTM zone group name, e.g. (16.6, 48.25) -> '33N'."""
    zone = int((lon + 180.0) // 6.0) + 1
    return f"{zone:02d}{'N' if lat >= 0 else 'S'}"


def net_rx_bytes() -> int | None:
    """Received bytes on non-loopback interfaces (Linux only); best-effort wire accounting."""
    try:
        total = 0
        for line in Path("/proc/net/dev").read_text().splitlines()[2:]:
            name, _, rest = line.partition(":")
            if name.strip() != "lo":
                total += int(rest.split()[0])
        return total
    except (OSError, ValueError, IndexError):
        return None


# --------------------------------------------------------------------------- windowing


def group_affine(ds: xr.Dataset) -> Affine:
    """Affine of the whole group, from ``spatial:transform`` (pixel-corner origin)."""
    a, b, c, d, e, f = ds.attrs["spatial:transform"]
    return Affine(a, b, c, d, e, f)


def bbox_to_window(ds: xr.Dataset, bbox_wgs84: BBox) -> tuple[slice, slice, Affine]:
    """(northing slice, easting slice, window affine) covering ``bbox_wgs84`` (lon/lat)."""
    west, south, east, north = bbox_wgs84
    crs = CRS.from_user_input(ds.attrs["crs"])
    to_utm = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    # densify edges: a lon/lat rectangle is not a UTM rectangle
    xmin, ymin, xmax, ymax = to_utm.transform_bounds(west, south, east, north, densify_pts=21)
    aff = group_affine(ds)
    n_rows, n_cols = ds.sizes["northing"], ds.sizes["easting"]
    col0 = max(0, math.floor((xmin - aff.c) / aff.a))
    col1 = min(n_cols, math.ceil((xmax - aff.c) / aff.a))
    row0 = max(0, math.floor((ymax - aff.f) / aff.e))  # e < 0: north-up
    row1 = min(n_rows, math.ceil((ymin - aff.f) / aff.e))
    if col1 <= col0 or row1 <= row0:
        raise ValueError(f"bbox {bbox_wgs84} falls outside the group's extent")
    window_aff = aff * Affine.translation(col0, row0)
    return slice(row0, row1), slice(col0, col1), window_aff


def n_inner_chunks(rows: slice, cols: slice) -> int:
    """Number of 256x256 inner chunks (per year, per array) the window touches."""
    nr = (rows.stop - 1) // INNER_CHUNK - rows.start // INNER_CHUNK + 1
    nc = (cols.stop - 1) // INNER_CHUNK - cols.start // INNER_CHUNK + 1
    return nr * nc


# --------------------------------------------------------------------------- reading


@dataclass
class YearTiming:
    year: int
    cold_s: float
    warm_s: float
    cold_bytes: int | None
    warm_bytes: int | None


@dataclass
class AoiRead:
    """Everything read for one AOI. ``emb`` is (year, band, y, x) float32, NaN = not embedded."""

    emb: np.ndarray
    transform: Affine
    crs: CRS
    years: list[int]
    group: str
    rows: slice
    cols: slice
    qc: dict[str, np.ndarray] = field(default_factory=dict)  # name -> (year, y, x[, month])
    timings: list[YearTiming] = field(default_factory=list)
    all_zero_int8_px: int = 0


def _check_single_zone(bbox_wgs84: BBox) -> str:
    west, south, east, north = bbox_wgs84
    g_sw, g_ne = zone_group_for(west, south), zone_group_for(east, north)
    if g_sw != g_ne:
        raise NotImplementedError(
            f"bbox spans zones {g_sw}/{g_ne}; stitch per-zone reads (neighbouring groups "
            "overlap by up to one tile, take each point from the zone whose 6-degree band "
            "contains it)"
        )
    return g_sw


def _read_year(
    ds: xr.Dataset, t_idx: int, rows: slice, cols: slice, with_qc: bool
) -> dict[str, np.ndarray]:
    """Blocking read of one year's window; embeddings come back as (y, x, band) int8."""
    names = ["embeddings", "scales", *(QC_COUNTS + QC_MONTHS if with_qc else ())]
    sub = ds[names].isel(time=t_idx, northing=rows, easting=cols)
    return {n: sub[n].values for n in names}


def _timed(fn: Callable[..., Any], *args: Any) -> tuple[Any, float, int | None]:
    rx0, t0 = net_rx_bytes(), time.perf_counter()
    out = fn(*args)
    dt = time.perf_counter() - t0
    rx1 = net_rx_bytes()
    return out, dt, (None if rx0 is None or rx1 is None else rx1 - rx0)


def read_aoi(
    bbox_wgs84: BBox,
    years: tuple[int, ...] | list[int],
    *,
    with_qc: bool = True,
    measure_warm: bool = False,
    ds: xr.Dataset | None = None,
) -> AoiRead:
    """Slice, read and dequantise ``bbox_wgs84`` for ``years`` from the right zone group."""
    group = _check_single_zone(bbox_wgs84)
    ds = ds if ds is not None else open_group(group)
    complete = set(ds.attrs["years_complete"])
    missing = [y for y in years if y not in complete]
    if missing:  # a preallocated slot reads back as fill instead of erroring
        raise ValueError(f"years {missing} not in years_complete {sorted(complete)} for {group}")
    rows, cols, transform = bbox_to_window(ds, bbox_wgs84)
    time_years = ds["time"].dt.year.values.tolist()
    qc_names = (*QC_COUNTS, *QC_MONTHS) if with_qc else ()

    emb_years: list[np.ndarray] = []
    qc_acc: dict[str, list[np.ndarray]] = {}
    timings: list[YearTiming] = []
    n_zero = 0
    t_idxs = [time_years.index(y) for y in years]
    if measure_warm:  # diagnostic mode: sequential, each year read twice
        fetched = []
        for year, t_idx in zip(years, t_idxs, strict=True):
            data, cold_s, cold_b = _timed(_read_year, ds, t_idx, rows, cols, with_qc)
            _, warm_s, warm_b = _timed(_read_year, ds, t_idx, rows, cols, with_qc)
            timings.append(YearTiming(year, cold_s, warm_s, cold_b, warm_b))
            fetched.append(data)
    else:  # years are independent fetches: overlap them (~3x faster than sequential)
        with ThreadPoolExecutor(max_workers=min(len(t_idxs), 8)) as pool:
            fetched = list(pool.map(lambda t: _read_year(ds, t, rows, cols, with_qc), t_idxs))
    for data in fetched:
        # scales is (y, x) float32: NaN = not embedded, maybe +inf = slot never written.
        # Non-finite scale => NaN vector (never a misleading 0).
        scales = data["scales"]
        safe = np.where(np.isfinite(scales), scales, np.nan)
        n_zero += int(
            (data["embeddings"].reshape(-1, data["embeddings"].shape[-1]) == 0).all(axis=1).sum()
        )
        deq = data["embeddings"].astype(np.float32) * safe[..., None]
        emb_years.append(np.ascontiguousarray(np.moveaxis(deq, -1, 0)))  # (band, y, x)
        for n in qc_names:
            qc_acc.setdefault(n, []).append(data[n])
        qc_acc.setdefault("scales", []).append(scales)
    return AoiRead(
        emb=np.stack(emb_years),
        transform=transform,
        crs=CRS.from_user_input(ds.attrs["crs"]),
        years=list(years),
        group=group,
        rows=rows,
        cols=cols,
        qc={n: np.stack(v) for n, v in qc_acc.items()},
        timings=timings,
        all_zero_int8_px=n_zero,
    )


def read_embeddings(
    bbox_wgs84: BBox, years: tuple[int, ...] | list[int]
) -> tuple[np.ndarray, Affine, CRS]:
    """Reusable entry point: ``(array[year, band, y, x] float32, transform, crs)``.

    ``bbox_wgs84`` is (west, south, east, north) in EPSG:4326. The window is snapped OUT to the
    10 m grid, so ``transform`` (pixel-corner origin, north-up) georeferences the array in the
    zone's UTM ``crs``. NaN marks pixels without embeddings (water / too few S2 observations).
    """
    r = read_aoi(bbox_wgs84, years, with_qc=False)
    return r.emb, r.transform, r.crs


# --------------------------------------------------------------------------- analysis


def cosine_distance(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Per-pixel cosine distance between two (band, y, x) arrays; NaN where either is NaN."""
    dot = (a * b).sum(axis=0)
    den = np.linalg.norm(a, axis=0) * np.linalg.norm(b, axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        return (1.0 - dot / den).astype(np.float32)


def pca_rgb(emb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """PCA(3) false colour of (band, y, x). Returns (uint8 (3, y, x), valid mask, var ratio).

    Valid pixels are scaled to 1..255 so 0 can act as GeoTIFF nodata.
    """
    n_band, h, w = emb.shape
    flat = emb.reshape(n_band, -1).T  # (pixels, band)
    valid = np.isfinite(flat).all(axis=1)
    x = flat[valid].astype(np.float64)
    x -= x.mean(axis=0)
    eigval, eigvec = np.linalg.eigh(np.cov(x, rowvar=False))
    order = np.argsort(eigval)[::-1][:3]
    scores = x @ eigvec[:, order]
    ratio = eigval[order] / eigval.sum()
    out = np.zeros((3, h * w), dtype=np.uint8)
    for i in range(3):
        lo, hi = np.percentile(scores[:, i], [2, 98])
        out[i, valid] = (1 + np.clip((scores[:, i] - lo) / (hi - lo), 0, 1) * 254).astype(np.uint8)
    return out.reshape(3, h, w), valid.reshape(h, w), ratio


def write_rgb_geotiff(path: Path, rgb: np.ndarray, transform: Affine, crs: CRS) -> None:
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=rgb.shape[1],
        width=rgb.shape[2],
        count=3,
        dtype="uint8",
        crs=crs,
        transform=transform,
        nodata=0,
        compress="deflate",
        photometric="RGB",
    ) as dst:
        dst.write(rgb)


# --------------------------------------------------------------------------- reporting


def describe_schema(ds: xr.Dataset, group: str) -> None:
    print(f"\n=== schema of group {group} ===")
    print(f"dims: {dict(ds.sizes)}")
    print("variables (dtype, dims, inner chunk):")
    for n, v in ds.data_vars.items():
        print(f"  {n:24s} {v.dtype!s:8s} {v.dims} chunks={v.encoding.get('chunks')}")
    print(f"coords: {list(ds.coords)}")
    skip = {"proj:wkt2", "proj:projjson", "runs", "zarr_conventions"}
    for k, v in ds.attrs.items():
        if k not in skip:
            print(f"  attr {k}: {v}")
    aff = group_affine(ds)
    e, n = ds["easting"].values, ds["northing"].values
    print(f"affine {tuple(aff)[:6]} -> pixel {aff.a} x {aff.e} m, origin is the pixel CORNER")
    print(f"easting  centres {e[0]}..{e[-1]} step {e[1] - e[0]:+.0f} (ascending)")
    print(f"northing centres {n[0]}..{n[-1]} step {n[1] - n[0]:+.0f} (DESCENDING, north-up)")
    centre_ok = np.isclose(e[0], aff.c + aff.a / 2) and np.isclose(n[0], aff.f + aff.e / 2)
    print(f"coords are pixel centres consistent with spatial:transform: {centre_ok}")
    print(f"time values: {[str(t)[:10] for t in ds['time'].values]}")
    print(f"time_bnds:   {[(str(a)[:10], str(b)[:10]) for a, b in ds['time_bnds'].values]}")
    print(
        f"=> a 'year' is the CALENDAR year (time_convention={ds.attrs.get('time_convention')}):"
        " time label = Jan 1 start of [Jan 1, Jan 1 + 1y)"
    )
    latest = str(max(ds.attrs["years_complete"]))
    refl = ds.attrs["runs"][latest]["input_coverage"]["stores"]["reflectance"]
    print(f"run input window ({latest}): reflectance {refl['first']}..{refl['last']}")


def fmt_stats(a: np.ndarray) -> str:
    a = a[np.isfinite(a)]
    if a.size == 0:
        return "n/a"
    q = np.percentile(a, [1, 50, 99])
    return f"min={a.min():.4g} p1={q[0]:.4g} med={q[1]:.4g} p99={q[2]:.4g} max={a.max():.4g}"


def report_read(r: AoiRead) -> None:
    _, _, h, w = r.emb.shape
    print(f"\n=== AOI read: group {r.group}, window rows {r.rows} cols {r.cols} ===")
    print(f"shape (year, band, y, x) = {r.emb.shape}; {h * w} px/year = {h * w * 1e-4:.2f} km2")
    print(f"affine {tuple(r.transform)[:6]} crs {r.crs.to_string()}")
    print(f"inner chunks touched per array per year: {n_inner_chunks(r.rows, r.cols)}")
    print(f"dequantised float32 size: {r.emb.nbytes / 1e6:.0f} MB")
    for i, y in enumerate(r.years):
        scales = r.qc["scales"][i]
        ok = np.isfinite(scales)
        print(
            f"[{y}] scales: NaN={float(np.isnan(scales).mean()):.4%} "
            f"+inf={float(np.isposinf(scales).mean()):.4%} {fmt_stats(scales)}"
        )
        print(f"       dequantised values: {fmt_stats(r.emb[i][:, ok])}")
        s2 = r.qc["s2_obs_count"][i]
        a1, d1 = r.qc["s1_asc_obs_count"][i], r.qc["s1_desc_obs_count"][i]
        low = float((s2[ok] < 25).mean()) if ok.any() else 0.0
        print(f"       s2_obs_count all px: {fmt_stats(s2.astype(float))}")
        print(
            f"       s2_obs_count embedded px: {fmt_stats(s2[ok].astype(float))}; <25 obs {low:.2%}"
        )
        print(
            f"       s2>0 but NaN scale: {int(((s2 > 0) & ~ok).sum())} px; "
            f"s2==0 but embedded: {int(((s2 == 0) & ok).sum())} px"
        )
        free = float(((a1 + d1 == 0) & ok).sum() / max(1, ok.sum()))
        print(
            f"       s1 asc obs: {fmt_stats(a1.astype(float))}; "
            f"desc: {fmt_stats(d1.astype(float))}; radar-free embedded px {free:.2%}"
        )
        for name in QC_MONTHS:
            m = r.qc[name][i]  # (y, x, 12) bool
            per_month = m[ok].mean(axis=0) if ok.any() else np.zeros(12)
            n_cov = m.sum(axis=-1)[ok]
            med = np.median(n_cov) if n_cov.size else 0
            print(
                f"       {name}: months/px median {med:.0f}; "
                f"frac px covered, month 1..12 = {np.round(per_month, 2).tolist()}"
            )
    print(f"all-zero int8 vectors (any year): {r.all_zero_int8_px}")


def report_timings(r: AoiRead) -> None:
    print("\n=== read latency (embeddings + scales + 3 count + 3 month arrays per year) ===")
    n_chunks = n_inner_chunks(r.rows, r.cols)
    for t in r.timings:
        cb = f"{t.cold_bytes / 1e6:.1f} MB" if t.cold_bytes is not None else "n/a"
        wb = f"{t.warm_bytes / 1e6:.1f} MB" if t.warm_bytes is not None else "n/a"
        print(
            f"  {t.year}: cold {t.cold_s:6.2f}s ({cb} rx), warm {t.warm_s:6.2f}s ({wb} rx), "
            f"{t.cold_s / n_chunks:.2f}s per emb-chunk cold"
        )
    cold = sum(t.cold_s for t in r.timings)
    print(f"  total cold {cold:.2f}s for {len(r.timings)} years x {n_chunks} chunks/array")


def main() -> None:
    p = argparse.ArgumentParser(description="TESSERA embeddings AOI read spike")
    p.add_argument("--bbox", type=float, nargs=4, default=DEFAULT_BBOX, metavar="DEG")
    p.add_argument("--years", type=int, nargs="+", default=list(DEFAULT_YEARS))
    p.add_argument("--pca-year", type=int, default=2024)
    p.add_argument("--out-dir", type=Path, default=Path("tessera_out"))
    args = p.parse_args()
    bbox: BBox = (args.bbox[0], args.bbox[1], args.bbox[2], args.bbox[3])
    args.out_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    repo = open_repo()
    t_open = time.perf_counter() - t0
    group = zone_group_for(bbox[0], bbox[1])
    t0 = time.perf_counter()
    ds = open_group(group, repo)
    print(f"open repo {t_open:.2f}s; open group {group} {time.perf_counter() - t0:.2f}s")
    describe_schema(ds, group)

    r = read_aoi(bbox, args.years, with_qc=True, measure_warm=True, ds=ds)
    report_read(r)
    report_timings(r)

    print("\n=== per-pixel year-over-year cosine distance (1 - cos) ===")
    dists = []
    for i in range(len(r.years) - 1):
        d = cosine_distance(r.emb[i], r.emb[i + 1])
        dists.append(d)
        print(
            f"  {r.years[i]}->{r.years[i + 1]}: valid={float(np.isfinite(d).mean()):.2%} "
            f"mean={float(np.nanmean(d)):.3f} {fmt_stats(d)}"
        )
    if dists:
        mean_d = np.nanmean(np.stack(dists), axis=0)
        print(f"  pixels with mean YoY distance > 0.5: {float(np.nanmean(mean_d > 0.5)):.2%}")
    else:
        print("  (fewer than 2 years: year-over-year summary skipped)")

    i = r.years.index(args.pca_year)
    rgb, valid, ratio = pca_rgb(r.emb[i])
    tif = args.out_dir / f"pca_{args.pca_year}.tif"
    write_rgb_geotiff(tif, rgb, r.transform, r.crs)
    print(
        f"\nPCA(3) {args.pca_year}: var ratio {np.round(ratio, 3).tolist()}, "
        f"valid {float(valid.mean()):.2%} -> {tif}"
    )

    npz = args.out_dir / "aoi_embeddings.npz"
    np.savez(
        npz,
        embeddings=r.emb,
        years=np.array(r.years),
        transform=np.array(tuple(r.transform)[:6]),
        crs_wkt=np.array(r.crs.to_wkt()),
        crs=np.array(r.crs.to_string()),
        bbox_wgs84=np.array(bbox),
        s2_obs_count=r.qc["s2_obs_count"],
        s1_asc_obs_count=r.qc["s1_asc_obs_count"],
        s1_desc_obs_count=r.qc["s1_desc_obs_count"],
    )
    print(f"saved {npz} ({npz.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
