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
from dataclasses import dataclass

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

from geogent_backend.geo.collections import COLLECTIONS, CollectionName, CollectionSpec
from geogent_backend.geo.indices import IndexName, get_spec
from geogent_backend.geo.raster import GDAL_ENV, _band_href, read_validity_mask
from geogent_backend.geo.reducers import ReducerName
from geogent_backend.geo.reducers import get_spec as get_reducer_spec


class CubeError(Exception):
    """Building or reducing a data cube failed (upstream/data problem)."""


def _target_epsg(scene_item: dict) -> int | None:
    props = scene_item.get("properties") or {}
    epsg = props.get("proj:epsg")
    return int(epsg) if epsg is not None else None


def decimal_years(dates: list[str]) -> np.ndarray:
    """ISO ``YYYY-MM-DD`` dates → decimal years, aligned with the cube's time
    axis (used by the trend reducer for an index-units-per-year slope)."""
    import datetime as _dt

    out: list[float] = []
    for d in dates:
        try:
            dd = _dt.date.fromisoformat(d)
            out.append(dd.year + (dd.timetuple().tm_yday - 1) / 365.25)
        except ValueError:
            out.append(0.0)
    return np.array(out, dtype="float64")


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


def write_single_band_cog(
    band: np.ndarray,
    crs: CRS,
    transform: Affine,
    description: str,
) -> bytes:
    """Write one float32 layer as a single-band GeoTIFF and return its bytes.

    v1 emits a **tiled GeoTIFF**, not a full COG layout (no overviews / COG
    driver yet), so don't assume HTTP-range/COG semantics — the small field
    rasters are read whole. Single-band (not multi-band) so each layer maps to
    one source URL, the shape the UI's MultiCOGLayer renders with a colormap.
    Moving to ``driver="COG"`` + object storage is a later step. NaN marks
    nodata; the UI discards NaN pixels in-shader.
    """
    height, width = band.shape
    profile: dict = {
        "driver": "GTiff",
        "dtype": "float32",
        "count": 1,
        "height": height,
        "width": width,
        "crs": crs,
        "transform": transform,
        "compress": "deflate",
        "nodata": float("nan"),
    }
    if width >= 256 and height >= 256:
        profile.update(tiled=True, blockxsize=256, blockysize=256)
    with MemoryFile() as mem:
        with mem.open(**profile) as dst:
            dst.write(band.astype("float32"), 1)
            dst.set_band_description(1, description)
        return bytes(mem.read())


@dataclass(frozen=True)
class CubeGrid:
    """The canonical grid every scene in a cube is warped onto.

    Shared by every cube built for the same AOI/resolution, which is what lets
    several index cubes stack into one aligned feature matrix (management
    zones) without a second alignment step.
    """

    epsg: int
    crs: CRS
    transform: Affine
    width: int
    height: int
    polygon_mask: np.ndarray  # True inside the AOI polygon

    @property
    def pixel_area_m2(self) -> float:
        return abs(self.transform.a * self.transform.e)


@dataclass(frozen=True)
class Cube:
    """A ``(time, y, x)`` index cube plus the provenance of how it got here."""

    values: np.ndarray
    dates: list[str]
    grid: CubeGrid
    index: IndexName
    collection_id: str
    n_scenes_found: int
    n_scenes_used: int
    n_scenes_failed: int
    n_scenes_cloud_masked: int

    @property
    def valid_obs_per_pixel(self) -> np.ndarray:
        return np.sum(np.isfinite(self.values), axis=0).astype("int32")


def _grid_for(
    geom_4326: dict, scene_items: list[dict], resolution_m: float
) -> tuple[CubeGrid, dict]:
    """Canonical grid: the first scene's UTM zone, the AOI bounds, at ``resolution_m``."""
    target_epsg = _target_epsg(scene_items[0])
    if target_epsg is None:
        raise CubeError("First scene has no proj:epsg; cannot define a target grid.")
    target_crs = CRS.from_epsg(target_epsg)

    geom_proj = transform_geom("EPSG:4326", target_crs, geom_4326)
    minx, miny, maxx, maxy = shape(geom_proj).bounds
    width = max(1, math.ceil((maxx - minx) / resolution_m))
    height = max(1, math.ceil((maxy - miny) / resolution_m))
    transform = Affine(resolution_m, 0.0, minx, 0.0, -resolution_m, maxy)
    polygon_mask = geometry_mask(
        [geom_proj], out_shape=(height, width), transform=transform, invert=True
    )
    return (
        CubeGrid(
            epsg=target_epsg,
            crs=target_crs,
            transform=transform,
            width=width,
            height=height,
            polygon_mask=polygon_mask,
        ),
        geom_proj,
    )


def build_cube(
    geom_4326: dict,
    scene_items: list[dict],
    index: IndexName,
    resolution_m: float = 10.0,
    collection: CollectionSpec | None = None,
    grid: CubeGrid | None = None,
) -> Cube:
    """Read every scene onto one grid and stack them into a ``(time, y, x)`` cube.

    BLOCKING: opens band COGs and warps each onto the canonical grid. Call via
    ``to_thread``. Pass ``grid`` to force a cube onto an existing grid — that is
    how several indices end up perfectly co-registered for zone clustering.
    """
    if not scene_items:
        raise CubeError("No scenes to build a cube from.")

    spec = get_spec(index)
    coll = collection or COLLECTIONS[CollectionName.sentinel_2_l2a]

    if grid is None:
        grid, _ = _grid_for(geom_4326, scene_items, resolution_m)

    layers: list[np.ndarray] = []
    dates: list[str] = []
    failed = 0
    masked_scenes = 0

    try:
        with rasterio.Env(**GDAL_ENV):
            polygon_mask = grid.polygon_mask
            vrt_opts = {
                "crs": grid.crs,
                "transform": grid.transform,
                "width": grid.width,
                "height": grid.height,
                "resampling": Resampling.nearest,
            }
            for item in scene_items:
                try:
                    bands: list[np.ndarray] = []
                    for key in spec.band_keys:
                        href = _band_href(item, coll.asset_key(key))
                        with rasterio.open(href) as src, WarpedVRT(src, **vrt_opts) as vrt:
                            # DN -> reflectance per collection (sensor-agnostic indices).
                            bands.append(vrt.read(1).astype("float32") * coll.scale + coll.offset)
                    values = spec.compute(*bands)
                    # Drop cloud/shadow/snow BEFORE stacking. This is what keeps
                    # the stability layer honest: unmasked cloud swings show up
                    # as temporal variance and fake within-field instability.
                    valid = read_validity_mask(item, coll, vrt_opts)
                    if valid is not None:
                        values = np.where(valid, values, np.nan).astype("float32")
                        masked_scenes += 1
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

    return Cube(
        values=np.stack(layers, axis=0),
        dates=dates,
        grid=grid,
        index=index,
        collection_id=coll.stac_id,
        n_scenes_found=len(scene_items),
        n_scenes_used=len(layers),
        n_scenes_failed=failed,
        n_scenes_cloud_masked=masked_scenes,
    )


def cube_provenance(cube: Cube, resolution_m: float) -> dict:
    """The "how much data is behind this" block every artifact summary carries."""
    n_obs = cube.valid_obs_per_pixel
    inside = cube.grid.polygon_mask & (n_obs > 0)
    obs_in = n_obs[inside]
    valid_obs = (
        {"min": int(obs_in.min()), "median": int(np.median(obs_in)), "max": int(obs_in.max())}
        if obs_in.size
        else {"min": 0, "median": 0, "max": 0}
    )
    used_dates = sorted(d for d in cube.dates if d)
    return {
        "index": cube.index.value,
        "collection": cube.collection_id,
        "n_scenes_found": cube.n_scenes_found,
        "n_scenes_used": cube.n_scenes_used,
        "n_scenes_failed": cube.n_scenes_failed,
        "n_scenes_cloud_masked": cube.n_scenes_cloud_masked,
        "time_span": [used_dates[0], used_dates[-1]] if used_dates else None,
        "grid": {
            "epsg": cube.grid.epsg,
            "resolution_m": resolution_m,
            "width": cube.grid.width,
            "height": cube.grid.height,
        },
        "valid_obs": valid_obs,
    }


def build_reduction(
    geom_4326: dict,
    scene_items: list[dict],
    index: IndexName,
    reducer: ReducerName,
    resolution_m: float = 10.0,
    params: dict | None = None,
    collection: CollectionSpec | None = None,
) -> tuple[dict, dict[str, bytes]]:
    """Build the season cube and apply ``reducer`` to it per pixel.

    BLOCKING: call via ``to_thread``. Returns ``(summary_dict,
    {output_name: cog_bytes})`` — one single-band GeoTIFF per reducer output.
    """
    params = params or {}
    rspec = get_reducer_spec(reducer)
    cube = build_cube(geom_4326, scene_items, index, resolution_m, collection)

    outputs = rspec.reduce(cube.values, decimal_years(cube.dates), params)
    inside = cube.grid.polygon_mask & (cube.valid_obs_per_pixel > 0)

    summary = {
        "reducer": reducer.value,
        **cube_provenance(cube, resolution_m),
        "outputs": {out.name: _feature_stats(outputs[out.name], inside) for out in rspec.outputs},
    }
    cogs = {
        out.name: write_single_band_cog(
            outputs[out.name], cube.grid.crs, cube.grid.transform, out.name
        )
        for out in rspec.outputs
    }
    return summary, cogs
