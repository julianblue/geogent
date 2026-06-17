"""PoC: a small multi-temporal NDVI data cube + per-pixel "field memory".

Spike for issue #65 (ADR 0002). NOT production code — no FastAPI wiring, no
auth, no artifact registry, no object storage. The point is to de-risk the
M1 cube path before we commit to it: prove that we can

  1. discover a season of Sentinel-2 scenes for one field (STAC, as today),
  2. windowed-read each scene and stack NDVI into a (time, y, x) cube
     **on a single canonical pixel grid**, then
  3. reduce that cube *per pixel over time* into the two "field memory"
     layers ADR 0002 leads with — productivity (multi-date mean NDVI) and
     stability (temporal coefficient of variation) — and
  4. write the result as a GeoTIFF the deck.gl-geotiff path can render,

and to measure what that costs (bytes moved, latency) versus the per-scene
scalar path we ship today.

It deliberately does NOT cluster into zones (that is M3) and does NOT do
per-pixel SCL cloud masking or cross-tile reprojection (those are the M1/M2
"align layer to cube grid" steps, flagged below). Scenes whose grid does not
match the canonical grid are skipped and counted, which is exactly the gap a
WarpedVRT/rioxarray resampling step closes in production.

Run (isolated venv, deps NOT added to the backend project):

    uv venv --python 3.12 /tmp/spike-venv
    uv pip install --python /tmp/spike-venv/bin/python \
        rasterio numpy shapely httpx
    /tmp/spike-venv/bin/python apps/backend/spikes/cube_zones/poc_field_memory_cube.py

The COGs live in the public AWS Open Data bucket over HTTPS, so no AWS
credentials are required; GDAL drives them as plain ``/vsicurl`` range reads.
"""

from __future__ import annotations

import os
import time
import warnings
from contextlib import contextmanager

import httpx
import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.warp import transform_geom
from rasterio.windows import Window, from_bounds
from shapely.geometry import shape

STAC_ROOT = "https://earth-search.aws.element84.com/v1"
COLLECTION = "sentinel-2-l2a"

# Same ~1.5 km Fresno County field block as the raster_compute spike, so the
# two PoCs are directly comparable.
FIELD_POLYGON = {
    "type": "Polygon",
    "coordinates": [
        [
            [-120.10, 36.80],
            [-120.10, 36.81],
            [-120.09, 36.81],
            [-120.09, 36.80],
            [-120.10, 36.80],
        ]
    ],
}

# A full growing season. A small field sits under a handful of MGRS tiles /
# relative orbits, so expect a few distinct grids in the results — see the
# "skipped (grid mismatch)" count the script prints.
SEASON_START = "2025-03-01"
SEASON_END = "2025-10-31"
MAX_CLOUD = 20.0
MAX_SCENES = 40

OUT_COG = "/tmp/field_memory.tif"

# Same GDAL-over-HTTP tuning as the production read path (geo/raster.py).
GDAL_ENV = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
    "GDAL_HTTP_MULTIRANGE": "YES",
    "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
    "VSI_CACHE": "TRUE",
    "VSI_CACHE_SIZE": "67108864",  # 64 MB
}

# Sandbox-only TLS workaround, identical to the raster_compute spike. The
# intercepting proxy's self-signed CA is not loaded by the wheel-bundled GDAL
# libcurl; point at the system bundle if present and, opt-in, skip verify so
# the spike can exercise the live read path. NEITHER belongs in production.
if os.path.exists("/etc/ssl/certs/ca-certificates.crt"):
    GDAL_ENV["GDAL_HTTP_CAINFO"] = "/etc/ssl/certs/ca-certificates.crt"
if os.environ.get("SPIKE_GDAL_UNSAFE_SSL") == "1":
    GDAL_ENV["GDAL_HTTP_UNSAFESSL"] = "YES"


@contextmanager
def timer(label: str):
    start = time.perf_counter()
    yield
    dt = time.perf_counter() - start
    print(f"  [{label}] {dt * 1000:.0f} ms")


def search_scenes(bbox: list[float]) -> list[dict]:
    """All low-cloud Sentinel-2 scenes for the field over the season, oldest
    first. Mirrors geo/stac.py:search_scenes — same catalog, filter, sort."""
    resp = httpx.post(
        f"{STAC_ROOT}/search",
        json={
            "collections": [COLLECTION],
            "bbox": bbox,
            "datetime": f"{SEASON_START}T00:00:00Z/{SEASON_END}T23:59:59Z",
            "query": {"eo:cloud_cover": {"lt": MAX_CLOUD}},
            "sortby": [{"field": "properties.datetime", "direction": "asc"}],
            "limit": MAX_SCENES,
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json().get("features") or []


def canonical_window(item: dict, geom_4326: dict) -> tuple[object, object, Window, dict]:
    """Derive the canonical (crs, full-scene transform, pixel window) from the
    first scene. Every other scene must match crs + transform to stack onto the
    same pixels without resampling — the same-grid invariant geo/raster.py
    already relies on, here extended across time."""
    with rasterio.Env(**GDAL_ENV), rasterio.open(item["assets"]["red"]["href"]) as ds:
        geom_utm = transform_geom("EPSG:4326", ds.crs, geom_4326)
        minx, miny, maxx, maxy = shape(geom_utm).bounds
        window = from_bounds(minx, miny, maxx, maxy, ds.transform).round_offsets().round_lengths()
        return ds.crs, ds.transform, window, geom_utm


def read_ndvi(item: dict, crs, transform, window: Window) -> np.ndarray | None:
    """Windowed NDVI for one scene on the canonical grid, or None if the scene
    sits on a different grid (different MGRS tile/origin). Returns float32 with
    NaN outside the valid index domain; polygon masking is applied by caller."""
    with rasterio.Env(**GDAL_ENV):
        with rasterio.open(item["assets"]["red"]["href"]) as red_ds:
            if (red_ds.crs, red_ds.transform) != (crs, transform):
                return None
            red = red_ds.read(1, window=window).astype("float32")
        with rasterio.open(item["assets"]["nir"]["href"]) as nir_ds:
            if (nir_ds.crs, nir_ds.transform) != (crs, transform):
                return None
            nir = nir_ds.read(1, window=window).astype("float32")
    denom = nir + red
    return np.where(denom > 0, (nir - red) / denom, np.nan).astype("float32")


def write_cog(path: str, productivity, stability, crs, win_transform) -> int:
    """Write the two field-memory layers as a 2-band tiled GeoTIFF. Production
    uses driver='COG' + object storage (ADR 0002 D1/D3); GTiff+tiled keeps the
    spike dependency-free while still being a valid windowed-read source."""
    h, w = productivity.shape
    profile = {
        "driver": "GTiff",
        "dtype": "float32",
        "count": 2,
        "height": h,
        "width": w,
        "crs": crs,
        "transform": win_transform,
        "tiled": True,
        "blockxsize": 256,
        "blockysize": 256,
        "compress": "deflate",
        "nodata": float("nan"),
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(productivity, 1)
        dst.write(stability, 2)
        dst.set_band_description(1, "productivity_mean_ndvi")
        dst.set_band_description(2, "stability_temporal_cv")
    return os.path.getsize(path)


def main() -> None:
    bbox = list(shape(FIELD_POLYGON).bounds)

    print("1. STAC search (season of low-cloud scenes for the field)")
    with timer("stac_search"):
        items = search_scenes(bbox)
    print(f"   found {len(items)} scenes  ({SEASON_START}..{SEASON_END}, cloud<{MAX_CLOUD:.0f})")
    if not items:
        raise SystemExit("No scenes found")

    crs, transform, window, geom_utm = canonical_window(items[0], FIELD_POLYGON)
    win_transform = rasterio.windows.transform(window, transform)
    h, w = int(window.height), int(window.width)
    print(f"   canonical grid: EPSG {crs.to_epsg()}, window {w}x{h} px")

    mask = geometry_mask([geom_utm], out_shape=(h, w), transform=win_transform, invert=True)

    print("\n2. Build the cube: windowed NDVI per scene, stacked on the grid")
    layers: list[np.ndarray] = []
    dates: list[str] = []
    skipped = 0
    with timer("build_cube_all_scenes"):
        for item in items:
            ndvi = read_ndvi(item, crs, transform, window)
            if ndvi is None or ndvi.shape != (h, w):
                skipped += 1
                continue
            ndvi = np.where(mask, ndvi, np.nan)  # restrict to the polygon
            layers.append(ndvi)
            dates.append(item["properties"]["datetime"][:10])
    if not layers:
        raise SystemExit("No scenes landed on the canonical grid")

    cube = np.stack(layers, axis=0)  # (time, y, x)
    print(f"   cube shape (t,y,x): {cube.shape}")
    print(f"   stacked {len(layers)} scenes, skipped {skipped} (grid mismatch)")
    print(f"   dates: {dates[0]} .. {dates[-1]}")
    print(f"   in-memory cube size: {cube.nbytes / 1e6:.2f} MB")

    print("\n3. Per-pixel temporal reduction -> 'field memory' layers")
    with timer("temporal_reduce"):
        # Pixels outside the polygon are all-NaN over time; nanmean/nanstd warn
        # on those empty slices. Expected — they are masked out below.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            productivity = np.nanmean(cube, axis=0)  # multi-date mean NDVI
            tstd = np.nanstd(cube, axis=0)
            stability = np.where(productivity > 0, tstd / productivity, np.nan)  # temporal CV
        n_obs = np.sum(~np.isnan(cube), axis=0)  # valid observations per pixel

    inside = mask & (n_obs > 0)
    prod_in = productivity[inside]
    cv_in = stability[inside]
    print(f"   pixels in polygon: {int(inside.sum())}")
    print(
        f"   valid obs/pixel: min {int(n_obs[inside].min())}, "
        f"median {int(np.median(n_obs[inside]))}, max {int(n_obs[inside].max())}"
    )
    print(
        f"   productivity (mean NDVI): mean {np.nanmean(prod_in):.3f}, "
        f"range [{np.nanmin(prod_in):.3f}, {np.nanmax(prod_in):.3f}]"
    )
    print(
        f"   stability (temporal CV):  mean {np.nanmean(cv_in):.3f}, "
        f"range [{np.nanmin(cv_in):.3f}, {np.nanmax(cv_in):.3f}]"
    )
    # The whole point of "field memory": within ONE field, pixels differ in
    # both how productive they are and how stable that is year-to-year. A flat
    # field would show near-zero spread here; spread => zones worth drawing.
    print(f"   within-field productivity spread (std): {np.nanstd(prod_in):.3f}")
    print(f"   within-field stability spread (std):    {np.nanstd(cv_in):.3f}")

    print("\n4. Write the field-memory layers as a (tiled) GeoTIFF")
    with timer("write_cog"):
        size = write_cog(OUT_COG, productivity, stability, crs, win_transform)
    print(
        f"   wrote {OUT_COG}: {size / 1e3:.1f} KB, 2 bands "
        f"(productivity_mean_ndvi, stability_temporal_cv)"
    )
    print("\n   -> this is the M1 'stability COG' artifact: a per-pixel product")
    print("      the existing deck.gl-geotiff layer renders with a colormap,")
    print("      and the input to M3 zone clustering.")


if __name__ == "__main__":
    main()
