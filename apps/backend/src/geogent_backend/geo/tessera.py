"""TESSERA yearly pixel embeddings: windowed reads from the public Icechunk store.

TESSERA v1.1 publishes one 128-d int8 embedding per 10 m pixel per **calendar
year** (2017+), quantised with a per-pixel float32 ``scales``, in a ~66 TiB
Icechunk (Zarr v3) store on AWS Open Data, one group per UTM zone + hemisphere
(``33N``). It can only ever be read in windows. This module is the provider
seam (ADR 0003), ported from ``spikes/tessera_embeddings``:

- pure helpers — zone naming, bbox → array window, bbox padding — that unit-test
  offline and import nothing heavy;
- the :class:`TesseraReader` Protocol the service depends on (tests inject a
  fake); and
- :class:`IcechunkTesseraReader`, the production implementation. icechunk /
  xarray / zarr are imported **lazily** (the ``embeddings`` dependency group), so
  the API boots without them and the routes answer 503 instead.

All reads are BLOCKING — callers offload them with ``anyio.to_thread``.
"""

from __future__ import annotations

import importlib.util
import math
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

import numpy as np
from affine import Affine
from rasterio.crs import CRS
from rasterio.warp import transform_bounds

if TYPE_CHECKING:  # pragma: no cover - typing only; real imports stay lazy
    import icechunk
    import xarray as xr

    from geogent_backend.config import Settings

BBox = tuple[float, float, float, float]

RESOLUTION_M = 10.0
# A calendar year is one embedding: winter crops straddle two of them.
ASSUMED_WINDOW = "calendar year (Jan 1–Dec 31); winter crops straddle two embeddings"

# Re-open a zone group at most this often: the cached readonly session is a
# snapshot, so a TTL lets a new store run (e.g. a freshly completed year) show up
# without restarting the process.
_GROUP_TTL_SECONDS = 300.0


class TesseraError(Exception):
    """Reading the TESSERA store failed (upstream/data problem -> 502 / failed job)."""


class TesseraUnavailableError(TesseraError):
    """The TESSERA reader cannot run here (disabled, or icechunk not installed -> 503)."""


class TesseraZoneError(TesseraError):
    """The window spans two UTM zones, which the reader does not stitch (-> 422)."""


class TesseraNoDataError(TesseraError):
    """The window holds no embedded pixels (outside coverage, water, ...)."""


# --------------------------------------------------------------------------- pure helpers


def zone_group_for(lon: float, lat: float) -> str:
    """Nominal 6° UTM zone group name, e.g. ``(16.6, 48.25) -> '33N'``."""
    zone = int((lon + 180.0) // 6.0) + 1
    return f"{zone:02d}{'N' if lat >= 0 else 'S'}"


def bbox_zone_group(bbox_wgs84: BBox) -> str:
    """Group a WGS84 bbox reads from; raises :class:`TesseraZoneError` if it
    crosses a zone boundary. Neighbouring groups overlap by at most one tile, so
    reading from the nominal zone of the corners is safe; stitching is not done."""
    west, south, east, north = bbox_wgs84
    g_sw, g_ne = zone_group_for(west, south), zone_group_for(east, north)
    if g_sw != g_ne:
        raise TesseraZoneError(
            f"The area spans two UTM zones ({g_sw}/{g_ne}); TESSERA reads are per zone, "
            "so pick an area inside one zone."
        )
    return g_sw


def expand_bbox_m(bbox_wgs84: BBox, metres: float) -> BBox:
    """Grow a lon/lat bbox by ``metres`` on every side (lat-corrected degrees),
    clamped to the valid lon/lat range."""
    west, south, east, north = bbox_wgs84
    if metres <= 0:
        return bbox_wgs84
    dlat = metres / 110_540.0
    midlat = math.radians((south + north) / 2.0)
    dlon = metres / (111_320.0 * max(math.cos(midlat), 0.01))
    return (
        max(-180.0, west - dlon),
        max(-90.0, south - dlat),
        min(180.0, east + dlon),
        min(90.0, north + dlat),
    )


def bbox_to_window(
    bbox_wgs84: BBox, crs: CRS, group_affine: Affine, n_rows: int, n_cols: int
) -> tuple[slice, slice, Affine]:
    """``(northing slice, easting slice, window affine)`` covering ``bbox_wgs84``.

    The window is snapped OUT to the 10 m grid and clipped to the group extent.
    ``group_affine`` has a pixel-corner origin and is north-up (``e < 0``)."""
    west, south, east, north = bbox_wgs84
    # densify the edges: a lon/lat rectangle is not a UTM rectangle
    xmin, ymin, xmax, ymax = transform_bounds("EPSG:4326", crs, west, south, east, north, 21)
    aff = group_affine
    col0 = max(0, math.floor((xmin - aff.c) / aff.a))
    col1 = min(n_cols, math.ceil((xmax - aff.c) / aff.a))
    row0 = max(0, math.floor((ymax - aff.f) / aff.e))
    row1 = min(n_rows, math.ceil((ymin - aff.f) / aff.e))
    if col1 <= col0 or row1 <= row0:
        raise TesseraNoDataError(f"bbox {bbox_wgs84} falls outside the TESSERA group's extent")
    return slice(row0, row1), slice(col0, col1), aff * Affine.translation(col0, row0)


def dequantise(embeddings_i8: np.ndarray, scales: np.ndarray) -> np.ndarray:
    """``(y, x, band)`` int8 × ``(y, x)`` scales → ``(band, y, x)`` float32.

    A non-finite scale (NaN = never embedded, +inf = slot never written) gives a
    NaN vector, never a misleading 0."""
    safe = np.where(np.isfinite(scales), scales, np.nan).astype(np.float32)
    deq = embeddings_i8.astype(np.float32) * safe[..., None]
    return np.ascontiguousarray(np.moveaxis(deq, -1, 0))


# --------------------------------------------------------------------------- seam


@dataclass
class EmbeddingWindow:
    """One AOI window. ``emb`` is ``(year, band, y, x)`` float32, NaN = not embedded;
    ``transform`` is north-up with a pixel-corner origin in the zone's ``crs``."""

    emb: np.ndarray
    transform: Affine
    crs: CRS
    years: list[int]
    group: str


class TesseraReader(Protocol):
    """What the embedding service needs from the store (tests inject a fake)."""

    def years_complete(self, group: str) -> set[int]:
        """Years whose embeddings are fully written for ``group`` (unwritten
        preallocated slots read back as fill, so callers must check this)."""

    def read_window(self, bbox_wgs84: BBox, years: list[int], dim: int) -> EmbeddingWindow:
        """Read + dequantise the first ``dim`` bands of ``bbox_wgs84`` for ``years``."""


# --------------------------------------------------------------------------- icechunk reader


def ensure_available() -> None:
    """Raise :class:`TesseraUnavailableError` unless the ``embeddings`` group is installed."""
    missing = [m for m in ("icechunk", "xarray", "zarr") if importlib.util.find_spec(m) is None]
    if missing:
        raise TesseraUnavailableError(
            f"TESSERA support is not installed (missing: {', '.join(missing)}); "
            "install the `embeddings` dependency group."
        )


class IcechunkTesseraReader:
    """Anonymous windowed reads from the TESSERA Icechunk store.

    ``repo_factory`` is the injection point: tests return an in-memory repo, the
    default opens the public S3 bucket. The repo is opened once; zone groups are
    cached for ``_GROUP_TTL_SECONDS`` because opening one costs ~2 s.
    """

    def __init__(
        self,
        *,
        bucket: str = "tessera-embeddings",
        prefix: str = "v1.1/dclimate.icechunk",
        region: str = "us-west-2",
        branch: str = "main",
        year_threads: int = 4,
        repo_factory: Callable[[], icechunk.Repository] | None = None,
    ) -> None:
        self._bucket, self._prefix, self._region = bucket, prefix, region
        self._branch = branch
        self._year_threads = max(1, year_threads)
        self._repo_factory = repo_factory or self._open_public_repo
        self._lock = threading.Lock()
        self._repo: icechunk.Repository | None = None
        self._groups: dict[str, tuple[float, xr.Dataset]] = {}

    def _open_public_repo(self) -> icechunk.Repository:
        import icechunk

        # Pass NO config object: the store ships reader-tuned settings.
        storage = icechunk.s3_storage(
            bucket=self._bucket, prefix=self._prefix, region=self._region, anonymous=True
        )
        return icechunk.Repository.open(storage)

    def _dataset(self, group: str) -> xr.Dataset:
        """Lazy xarray view of one zone group (``chunks=None``: no dask graph over
        millions of chunks — always ``isel`` before ``.values``)."""
        import xarray as xr

        with self._lock:
            hit = self._groups.get(group)
            if hit is not None and time.monotonic() - hit[0] < _GROUP_TTL_SECONDS:
                return hit[1]
            if self._repo is None:
                self._repo = self._repo_factory()
            session = self._repo.readonly_session(branch=self._branch)
            ds = xr.open_zarr(
                session.store, group=group, consolidated=False, decode_coords="all", chunks=None
            )
            self._groups[group] = (time.monotonic(), ds)
            return ds

    def years_complete(self, group: str) -> set[int]:
        ensure_available()
        try:
            return {int(y) for y in self._dataset(group).attrs["years_complete"]}
        except TesseraError:
            raise
        except Exception as exc:  # noqa: BLE001 - icechunk/zarr/botocore errors are all "upstream"
            raise TesseraError(f"could not open TESSERA group {group}: {exc}") from exc

    def read_window(self, bbox_wgs84: BBox, years: list[int], dim: int) -> EmbeddingWindow:
        ensure_available()
        group = bbox_zone_group(bbox_wgs84)
        try:
            return self._read_window(group, bbox_wgs84, years, dim)
        except TesseraError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise TesseraError(f"TESSERA read failed for group {group}: {exc}") from exc

    def _read_window(
        self, group: str, bbox_wgs84: BBox, years: list[int], dim: int
    ) -> EmbeddingWindow:
        ds = self._dataset(group)
        crs = CRS.from_user_input(ds.attrs["crs"])
        a, b, c, d, e, f = ds.attrs["spatial:transform"]
        rows, cols, transform = bbox_to_window(
            bbox_wgs84,
            crs,
            Affine(a, b, c, d, e, f),
            ds.sizes["northing"],
            ds.sizes["easting"],
        )
        time_years = ds["time"].dt.year.values.tolist()
        missing = [y for y in years if y not in time_years]
        if missing:
            raise TesseraError(f"years {missing} are not in the TESSERA store")
        t_idxs = [time_years.index(y) for y in years]

        def read_year(t_idx: int) -> np.ndarray:
            sub = ds[["embeddings", "scales"]].isel(
                time=t_idx, northing=rows, easting=cols, band=slice(0, dim)
            )
            return dequantise(sub["embeddings"].values, sub["scales"].values)

        # Years are independent fetches: overlapping them is ~3x faster than serial.
        with ThreadPoolExecutor(max_workers=min(len(t_idxs), self._year_threads)) as pool:
            per_year = list(pool.map(read_year, t_idxs))
        return EmbeddingWindow(
            emb=np.stack(per_year), transform=transform, crs=crs, years=list(years), group=group
        )


def reader_from_settings(settings: Settings) -> IcechunkTesseraReader:
    """Build the production reader from :class:`~geogent_backend.config.Settings`."""
    return IcechunkTesseraReader(
        bucket=settings.tessera_bucket,
        prefix=settings.tessera_prefix,
        region=settings.tessera_region,
        branch=settings.tessera_branch,
        year_threads=settings.tessera_year_threads,
    )
