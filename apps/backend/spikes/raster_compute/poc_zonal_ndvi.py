"""PoC: zonal mean NDVI for one polygon over one Sentinel-2 scene.

Spike for issue #28. NOT production code — no FastAPI wiring, no auth, no
caching. The point is to prove the windowed-COG read path works against the
same Earth Search STAC catalog the UI already uses, and to measure the
latency difference between a windowed read (only the polygon's pixels) and a
naive full-band fetch.

Run (isolated venv, deps NOT added to the backend project):

    uv venv --python 3.12 /tmp/spike-venv
    uv pip install --python /tmp/spike-venv/bin/python \
        rasterio rasterstats numpy shapely httpx
    /tmp/spike-venv/bin/python apps/backend/spikes/raster_compute/poc_zonal_ndvi.py

The COGs live in the AWS Open Data bucket and are public over HTTPS, so no
AWS credentials are required — we read them via GDAL's /vsicurl with the
``aws_unsigned`` virtual filesystem turned off (plain HTTPS range reads).
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager

import httpx
import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.warp import transform_geom
from rasterio.windows import from_bounds
from shapely.geometry import shape

STAC_ROOT = "https://earth-search.aws.element84.com/v1"
COLLECTION = "sentinel-2-l2a"

# A ~1.5 km field block in California's Central Valley (Fresno County), a
# heavily irrigated agricultural area — guaranteed Sentinel-2 coverage and a
# real polygon a user might draw over a farm.
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

# GDAL tuning for COG-over-HTTP. These are the knobs that make windowed reads
# fast: don't list sibling files, merge nearby ranges into one GET, cache the
# header block so the second band read doesn't re-fetch the IFD.
GDAL_ENV = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
    "GDAL_HTTP_MULTIRANGE": "YES",
    "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
    "VSI_CACHE": "TRUE",
    "VSI_CACHE_SIZE": "67108864",  # 64 MB
}

# In the sandboxed CI/web container, outbound HTTPS goes through an
# intercepting proxy whose self-signed CA the bundled GDAL libcurl won't
# load via GDAL_HTTP_CAINFO. Point it at the system bundle if present, and
# fall back to skipping verification so the spike can still exercise the read
# path. NEITHER of these belongs in the production read path — there the
# default system trust store works against AWS's real certs.
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


def find_scene(bbox: list[float]) -> dict:
    """Most-recent low-cloud Sentinel-2 scene intersecting bbox.

    Mirrors apps/ui/src/lib/sentinel2.ts: same catalog, same cloud filter,
    same sort. Returns the full STAC item (we need the band hrefs).
    """
    resp = httpx.post(
        f"{STAC_ROOT}/search",
        json={
            "collections": [COLLECTION],
            "bbox": bbox,
            "query": {"eo:cloud_cover": {"lt": 20}},
            "sortby": [{"field": "properties.datetime", "direction": "desc"}],
            "limit": 1,
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    features = resp.json().get("features") or []
    if not features:
        raise SystemExit("No matching Sentinel-2 scene found")
    return features[0]


def zonal_mean_ndvi_windowed(red_href: str, nir_href: str, geom_4326: dict) -> dict:
    """Windowed read: fetch ONLY the COG blocks covering the polygon.

    GDAL translates the polygon's projected bounds into a pixel window and
    issues HTTP range requests for just the tiles that intersect it. For a
    ~1.5 km polygon on a 110 km, 10 m scene that's a handful of 1024px
    internal tiles, not the whole ~120 MB band.
    """
    with rasterio.Env(**GDAL_ENV):
        with rasterio.open(red_href) as red_ds:
            # Reproject the WGS84 polygon into the scene's UTM CRS.
            geom_utm = transform_geom("EPSG:4326", red_ds.crs, geom_4326)
            minx, miny, maxx, maxy = shape(geom_utm).bounds
            window = from_bounds(minx, miny, maxx, maxy, red_ds.transform)
            red = red_ds.read(1, window=window).astype("float32")
            win_transform = red_ds.window_transform(window)

        with rasterio.open(nir_href) as nir_ds:
            window_nir = from_bounds(minx, miny, maxx, maxy, nir_ds.transform)
            nir = nir_ds.read(1, window=window_nir).astype("float32")

    # Both 10 m bands share the grid, so windows align. Guard anyway.
    h = min(red.shape[0], nir.shape[0])
    w = min(red.shape[1], nir.shape[1])
    red, nir = red[:h, :w], nir[:h, :w]

    mask = geometry_mask(
        [geom_utm],
        out_shape=(h, w),
        transform=win_transform,
        invert=True,  # True == inside polygon
    )

    denom = nir + red
    valid = mask & (denom > 0)
    ndvi = np.where(denom > 0, (nir - red) / denom, np.nan)
    inside = ndvi[valid]

    return {
        "window_px": f"{w}x{h}",
        "pixels_in_polygon": int(valid.sum()),
        "ndvi_mean": float(np.nanmean(inside)) if inside.size else float("nan"),
        "ndvi_min": float(np.nanmin(inside)) if inside.size else float("nan"),
        "ndvi_max": float(np.nanmax(inside)) if inside.size else float("nan"),
    }


def full_band_bytes(href: str) -> int:
    """Content-Length of a band asset — the cost of a naive full fetch.

    We deliberately do NOT download it; HEAD is enough to contrast against
    the windowed read's range requests.
    """
    resp = httpx.head(href, follow_redirects=True, timeout=30.0)
    resp.raise_for_status()
    return int(resp.headers.get("Content-Length", 0))


def main() -> None:
    bbox = [
        FIELD_POLYGON["coordinates"][0][0][0],
        FIELD_POLYGON["coordinates"][0][0][1],
        FIELD_POLYGON["coordinates"][0][2][0],
        FIELD_POLYGON["coordinates"][0][2][1],
    ]

    print("1. STAC search (Earth Search v1, sentinel-2-l2a, cloud<20, newest)")
    with timer("stac_search"):
        item = find_scene(bbox)
    print(f"   scene: {item['id']}")
    print(f"   datetime: {item['properties']['datetime']}")
    print(f"   cloud_cover: {item['properties'].get('eo:cloud_cover'):.1f}%")
    print(f"   crs (proj:epsg): {item['properties'].get('proj:epsg')}")

    red_href = item["assets"]["red"]["href"]
    nir_href = item["assets"]["nir"]["href"]
    print(f"   red (B04): {red_href}")
    print(f"   nir (B08): {nir_href}")

    print("\n2. Windowed COG read + zonal NDVI (range reads, polygon only)")
    with timer("windowed_zonal_ndvi"):
        result = zonal_mean_ndvi_windowed(red_href, nir_href, FIELD_POLYGON)
    for k, v in result.items():
        print(f"   {k}: {v}")

    print("\n3. Full-band size (what a naive 'download the whole band' costs)")
    with timer("head_red"):
        red_bytes = full_band_bytes(red_href)
    with timer("head_nir"):
        nir_bytes = full_band_bytes(nir_href)
    total_mb = (red_bytes + nir_bytes) / 1e6
    print(f"   red band: {red_bytes / 1e6:.1f} MB")
    print(f"   nir band: {nir_bytes / 1e6:.1f} MB")
    print(f"   full 2-band fetch would move ~{total_mb:.0f} MB; windowed read")
    print("   moves a few internal tiles + the COG header (~hundreds of KB).")


if __name__ == "__main__":
    main()
