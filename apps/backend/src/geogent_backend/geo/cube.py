"""Multi-temporal data cube + per-pixel "field memory" reduction.

Builds a ``(time, y, x)`` index cube for a field polygon by windowed-reading
each scene's bands over ``/vsicurl`` and **warping every scene onto one
canonical grid** with ``WarpedVRT`` (the M1 fix from ``spikes/cube_zones``:
without alignment, scenes on other MGRS tiles/orbits drop out and the season is
truncated). It then reduces the cube per pixel into two layers:

- **productivity** — the multi-date mean of the index (how good a pixel is), and
- **stability** — the temporal coefficient of variation (how consistent it is).

The cube is sub-MB at field scale (see the spike), so the reduction is plain
numpy — no xarray/dask needed yet (ADR 0002 D2). The blocking GDAL work lives in
:func:`build_field_memory`; callers offload it with ``anyio.to_thread.run_sync``
as the zonal path does. The pure-numpy reduction and the COG writer are split
out so they unit-test offline.
"""

from __future__ import annotations

import math
import warnings

import numpy as np
import rasterio
from affine import Affine
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.io import MemoryFile
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform_geom
from shapely.geometry import shape

from geogent_backend.geo.indices import IndexName, get_spec
from geogent_backend.geo.raster import GDAL_ENV, _band_href


class CubeError(Exception):
    """Building or reducing a data cube failed (upstream/data problem)."""


def _target_epsg(scene_item: dict) -> int | None:
    props = scene_item.get("properties") or {}
    epsg = props.get("proj:epsg")
    return int(epsg) if epsg is not None else None


def reduce_field_memory(
    cube: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Reduce a ``(time, y, x)`` index cube per pixel over time.

    Returns ``(productivity, stability, n_obs)`` as ``(y, x)`` arrays:
    productivity = nanmean over time, stability = temporal CV (std/mean, NaN
    where mean <= 0), n_obs = count of finite observations.
    """
    if cube.ndim != 3:
        raise CubeError("cube must be (time, y, x)")
    with warnings.catch_warnings():
        # All-NaN pixels (outside the polygon / fully cloudy) warn on nanmean;
        # expected — they are masked out by callers via the polygon/ n_obs.
        warnings.simplefilter("ignore", category=RuntimeWarning)
        productivity = np.nanmean(cube, axis=0).astype("float32")
        tstd = np.nanstd(cube, axis=0).astype("float32")
        stability = np.where(productivity > 0, tstd / productivity, np.nan).astype("float32")
    n_obs = np.sum(np.isfinite(cube), axis=0).astype("int32")
    return productivity, stability, n_obs


def _feature_stats(layer: np.ndarray, inside: np.ndarray) -> dict:
    vals = layer[inside]
    vals = vals[np.isfinite(vals)]
    if vals.size == 0:
        return {"mean": 0.0, "min": 0.0, "max": 0.0, "std": 0.0, "within_field_spread": 0.0}
    return {
        "mean": float(np.mean(vals)),
        "min": float(np.min(vals)),
        "max": float(np.max(vals)),
        "std": float(np.std(vals)),
        "within_field_spread": float(np.std(vals)),
    }


def write_feature_cog(
    productivity: np.ndarray,
    stability: np.ndarray,
    crs: CRS,
    transform: Affine,
) -> bytes:
    """Write the two field-memory layers as a 2-band GeoTIFF and return bytes.

    Production swaps ``driver="COG"`` + object storage; a tiled GTiff keeps v1
    dependency-free while remaining a valid windowed-read source for the UI.
    """
    height, width = productivity.shape
    profile: dict = {
        "driver": "GTiff",
        "dtype": "float32",
        "count": 2,
        "height": height,
        "width": width,
        "crs": crs,
        "transform": transform,
        "compress": "deflate",
        "nodata": float("nan"),
    }
    # Internal tiling only helps (and is only valid) once the raster is larger
    # than a tile; small field rasters are written stripped.
    if width >= 256 and height >= 256:
        profile.update(tiled=True, blockxsize=256, blockysize=256)
    with MemoryFile() as mem:
        with mem.open(**profile) as dst:
            dst.write(productivity.astype("float32"), 1)
            dst.write(stability.astype("float32"), 2)
            dst.set_band_description(1, "productivity_mean_index")
            dst.set_band_description(2, "stability_temporal_cv")
        return bytes(mem.read())


def build_field_memory(
    geom_4326: dict,
    scene_items: list[dict],
    index: IndexName,
    resolution_m: float = 10.0,
) -> tuple[dict, bytes]:
    """Build the season cube and reduce it to the field-memory layers.

    BLOCKING: opens band COGs and warps each onto the canonical grid. Call via
    ``to_thread``. Returns ``(summary_dict, cog_bytes)``.
    """
    if not scene_items:
        raise CubeError("No scenes to build a cube from.")

    spec = get_spec(index)

    # Canonical grid: the first scene's UTM zone, the field's bounds, at the
    # requested resolution. Every scene is warped onto exactly this grid.
    target_epsg = _target_epsg(scene_items[0])
    if target_epsg is None:
        raise CubeError("First scene has no proj:epsg; cannot define a target grid.")
    target_crs = CRS.from_epsg(target_epsg)

    geom_proj = transform_geom("EPSG:4326", target_crs, geom_4326)
    minx, miny, maxx, maxy = shape(geom_proj).bounds
    width = max(1, math.ceil((maxx - minx) / resolution_m))
    height = max(1, math.ceil((maxy - miny) / resolution_m))
    transform = Affine(resolution_m, 0.0, minx, 0.0, -resolution_m, maxy)

    layers: list[np.ndarray] = []
    dates: list[str] = []
    failed = 0

    try:
        with rasterio.Env(**GDAL_ENV):
            polygon_mask = geometry_mask(
                [geom_proj], out_shape=(height, width), transform=transform, invert=True
            )
            vrt_opts = {
                "crs": target_crs,
                "transform": transform,
                "width": width,
                "height": height,
                "resampling": Resampling.nearest,
            }
            for item in scene_items:
                try:
                    bands: list[np.ndarray] = []
                    for key in spec.band_keys:
                        href = _band_href(item, key)
                        with rasterio.open(href) as src, WarpedVRT(src, **vrt_opts) as vrt:
                            bands.append(vrt.read(1).astype("float32"))
                    values = spec.compute(*bands)
                    values = np.where(polygon_mask, values, np.nan).astype("float32")
                    layers.append(values)
                    props = item.get("properties") or {}
                    dates.append(str(props.get("datetime", ""))[:10])
                except Exception:  # noqa: BLE001 - one bad scene shouldn't fail the cube
                    failed += 1
                    continue
    except Exception as exc:  # GDAL env / mask construction
        raise CubeError(f"Failed to build cube: {exc}") from exc

    if not layers:
        raise CubeError("All scenes failed to read; cube is empty.")

    cube = np.stack(layers, axis=0)
    productivity, stability, n_obs = reduce_field_memory(cube)

    inside = polygon_mask & (n_obs > 0)
    obs_in = n_obs[inside]
    valid_obs = (
        {
            "min": int(obs_in.min()),
            "median": int(np.median(obs_in)),
            "max": int(obs_in.max()),
        }
        if obs_in.size
        else {"min": 0, "median": 0, "max": 0}
    )
    used_dates = sorted(d for d in dates if d)
    summary = {
        "index": index.value,
        "n_scenes_found": len(scene_items),
        "n_scenes_used": len(layers),
        "n_scenes_failed": failed,
        "time_span": [used_dates[0], used_dates[-1]] if used_dates else None,
        "grid": {
            "epsg": target_epsg,
            "resolution_m": resolution_m,
            "width": width,
            "height": height,
        },
        "valid_obs": valid_obs,
        "productivity": _feature_stats(productivity, inside),
        "stability": _feature_stats(stability, inside),
    }

    cog = write_feature_cog(productivity, stability, target_crs, transform)
    return summary, cog
