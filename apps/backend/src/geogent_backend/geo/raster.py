"""Windowed COG read + zonal statistics over a field polygon.

This is the thin seam the rest of the backend talks to for raster compute; if
we ever move to a TiTiler ``/statistics`` service, only this module changes.

The read path follows the de-risked spike (``spikes/raster_compute``): reproject
the WGS84 polygon into the scene CRS, derive ONE canonical integer pixel window,
read each band windowed over ``/vsicurl``, compute the index with numpy, mask to
the polygon, and reduce. Blocking/CPU + GDAL work lives here; callers offload it
with ``anyio.to_thread.run_sync`` so the event loop never blocks.
"""

from __future__ import annotations

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform_geom
from rasterio.windows import from_bounds
from shapely.geometry import shape

from geogent_backend.geo.collections import COLLECTIONS, CollectionName, CollectionSpec
from geogent_backend.geo.indices import IndexName, get_spec

# GDAL tuning for COG-over-HTTP windowed reads (from the spike, minus the
# sandbox-only SSL workaround — production uses the system trust store).
GDAL_ENV = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
    "GDAL_HTTP_MULTIRANGE": "YES",
    "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
    "VSI_CACHE": "TRUE",
    "VSI_CACHE_SIZE": "67108864",  # 64 MB
}


class RasterComputeError(Exception):
    """A windowed COG read or zonal reduction failed (upstream/data problem)."""


def _optional_band_href(scene_item: dict, key: str) -> str | None:
    """Href for an optional asset (e.g. the QA band), or None if absent."""
    asset = (scene_item.get("assets") or {}).get(key)
    href = asset.get("href") if asset else None
    return href or None


def read_validity_mask(
    scene_item: dict,
    coll: CollectionSpec,
    vrt_opts: dict,
) -> np.ndarray | None:
    """Read the collection's quality band onto the target grid → usable-pixel mask.

    Returns None when the collection declares no mask or the item is missing the
    quality asset; callers then proceed unmasked and report it, rather than
    failing an otherwise good scene. Nearest-neighbour resampling is deliberate:
    class codes and bit flags must not be interpolated.
    """
    if coll.mask is None:
        return None
    href = _optional_band_href(scene_item, coll.mask.asset_key)
    if href is None:
        return None
    with (
        rasterio.open(href) as src,
        WarpedVRT(src, **{**vrt_opts, "resampling": Resampling.nearest}) as vrt,
    ):
        return coll.mask.valid(vrt.read(1))


def _band_href(scene_item: dict, key: str) -> str:
    assets = scene_item.get("assets") or {}
    asset = assets.get(key)
    if not asset or not asset.get("href"):
        raise RasterComputeError(f"Scene is missing asset '{key}' required for this index.")
    return asset["href"]


def zonal_stats(
    geom_4326: dict,
    scene_item: dict,
    index: IndexName,
    histogram_bins: int = 20,
    collection: CollectionSpec | None = None,
) -> dict:
    """Compute zonal statistics for ``index`` over ``geom_4326`` within one scene.

    BLOCKING: opens band COGs and reads windows. Call via ``to_thread``.

    Cloud, shadow and snow pixels are dropped first (see ``masking.py``), so
    the statistics describe usable ground; ``valid_pixels`` is what survived and
    ``cloud_masked`` says whether a quality band was actually applied.

    Returns ``{mean, min, max, std, valid_pixels, nodata_pixels, cloud_masked,
    histogram: {bin_edges, counts}}``.
    """
    spec = get_spec(index)
    coll = collection or COLLECTIONS[CollectionName.sentinel_2_l2a]
    band_arrays: list[np.ndarray] = []
    geom_proj: dict | None = None
    win_transform = None
    valid_mask: np.ndarray | None = None

    try:
        with rasterio.Env(**GDAL_ENV):
            # Canonical grid from the first band: reproject the polygon into that
            # band's CRS and derive ONE integer pixel window. Every band is then
            # warped onto exactly this grid via WarpedVRT, so mixed-resolution
            # bands (e.g. 20 m swir for NBR/NDMI) line up without a same-grid
            # restriction.
            first_href = _band_href(scene_item, coll.asset_key(spec.band_keys[0]))
            with rasterio.open(first_href) as ds0:
                geom_proj = transform_geom("EPSG:4326", ds0.crs, geom_4326)
                minx, miny, maxx, maxy = shape(geom_proj).bounds
                window = (
                    from_bounds(minx, miny, maxx, maxy, ds0.transform)
                    .round_offsets()
                    .round_lengths()
                )
                win_transform = ds0.window_transform(window)
                target_crs = ds0.crs
                width, height = int(window.width), int(window.height)

            if width <= 0 or height <= 0:
                raise RasterComputeError("Polygon does not overlap the scene (empty read window).")

            vrt_opts = {
                "crs": target_crs,
                "transform": win_transform,
                "width": width,
                "height": height,
                "resampling": Resampling.nearest,
            }
            for key in spec.band_keys:
                href = _band_href(scene_item, coll.asset_key(key))
                with rasterio.open(href) as src, WarpedVRT(src, **vrt_opts) as vrt:
                    # Scale DN -> reflectance per collection so the index kernels
                    # (esp. EVI/SAVI) are sensor-agnostic.
                    band_arrays.append(vrt.read(1).astype("float32") * coll.scale + coll.offset)

            # Cloud/shadow mask on the same grid. Without it a shadowed corner
            # of the polygon silently drags the field mean down.
            valid_mask = read_validity_mask(scene_item, coll, vrt_opts)
    except RasterComputeError:
        raise
    except Exception as exc:  # rasterio / GDAL / network failures
        raise RasterComputeError(f"Failed to read scene COGs: {exc}") from exc

    if not band_arrays or band_arrays[0].size == 0:
        raise RasterComputeError("Polygon does not overlap the scene (empty read window).")

    values = spec.compute(*band_arrays)
    if valid_mask is not None:
        values = np.where(valid_mask, values, np.nan).astype("float32")
    h, w = values.shape

    assert geom_proj is not None and win_transform is not None
    polygon_mask = geometry_mask(
        [geom_proj],
        out_shape=(h, w),
        transform=win_transform,
        invert=True,  # True == inside polygon
    )

    inside = values[polygon_mask]
    finite = np.isfinite(inside)
    valid = inside[finite]
    valid_pixels = int(valid.size)
    nodata_pixels = int(inside.size - valid_pixels)

    if valid_pixels == 0:
        raise RasterComputeError(
            "No usable pixels inside the polygon — the field is fully clouded, "
            "shadowed or outside the scene. Try another date or raise max_cloud_cover."
        )

    counts, bin_edges = np.histogram(valid, bins=histogram_bins)

    return {
        "mean": float(np.mean(valid)),
        "min": float(np.min(valid)),
        "max": float(np.max(valid)),
        "std": float(np.std(valid)),
        "valid_pixels": valid_pixels,
        "nodata_pixels": nodata_pixels,
        "cloud_masked": valid_mask is not None,
        "histogram": {
            "bin_edges": [float(x) for x in bin_edges.tolist()],
            "counts": [int(x) for x in counts.tolist()],
        },
    }
