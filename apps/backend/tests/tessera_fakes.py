"""Shared fixtures for the TESSERA embedding tests: a planted-cluster window and a
fake :class:`TesseraReader` that serves it without any store or network."""

from __future__ import annotations

import numpy as np
from affine import Affine
from rasterio.crs import CRS
from rasterio.warp import transform_geom

from geogent_backend.geo.tessera import BBox, EmbeddingWindow

DIM = 8
# 60 x 60 px (600 m) window in UTM 33N near Marchfeld; the field is a 20 x 20 px
# (200 m = 4 ha) square in the middle.
X0, Y0 = 600_000.0, 5_340_000.0
SIZE = 60
FIELD_SLICE = slice(20, 40)
TRANSFORM = Affine(10.0, 0.0, X0, 0.0, -10.0, Y0)
CRS_UTM = CRS.from_epsg(32633)


def field_geometry_4326(inset_px: int = 0) -> dict:
    """GeoJSON polygon of the planted field in WGS84 (optionally shrunk)."""
    lo, hi = 20 + inset_px, 40 - inset_px
    ring = [
        (X0 + lo * 10, Y0 - lo * 10),
        (X0 + hi * 10, Y0 - lo * 10),
        (X0 + hi * 10, Y0 - hi * 10),
        (X0 + lo * 10, Y0 - hi * 10),
        (X0 + lo * 10, Y0 - lo * 10),
    ]
    return transform_geom(CRS_UTM, "EPSG:4326", {"type": "Polygon", "coordinates": [ring]})


def unit(i: int, dim: int = DIM) -> np.ndarray:
    v = np.zeros(dim, dtype=np.float32)
    v[i % dim] = 1.0
    return v


def planted_window(
    years: list[int],
    crops: dict[int, np.ndarray],
    offsets: dict[int, np.ndarray],
    *,
    noise: float = 0.01,
    seed: int = 0,
) -> EmbeddingWindow:
    """Per year: background = year offset + noise; field = year offset + crop vector."""
    rng = np.random.default_rng(seed)
    emb = np.empty((len(years), DIM, SIZE, SIZE), dtype=np.float32)
    for i, y in enumerate(years):
        base = offsets[y][:, None, None] + rng.normal(0, noise, (DIM, SIZE, SIZE))
        base[:, FIELD_SLICE, FIELD_SLICE] += crops[y][:, None, None]
        emb[i] = base
    return EmbeddingWindow(emb=emb, transform=TRANSFORM, crs=CRS_UTM, years=years, group="33N")


class FakeReader:
    """Serves one preset window; records the calls so tests can assert on them."""

    def __init__(self, window: EmbeddingWindow, complete: set[int] | None = None) -> None:
        self._window = window
        self._complete = set(window.years) if complete is None else complete
        self.read_calls: list[tuple[BBox, list[int], int]] = []

    def years_complete(self, group: str) -> set[int]:
        return self._complete

    def read_window(self, bbox_wgs84: BBox, years: list[int], dim: int) -> EmbeddingWindow:
        self.read_calls.append((bbox_wgs84, list(years), dim))
        idx = [self._window.years.index(y) for y in years]
        return EmbeddingWindow(
            emb=self._window.emb[idx, :dim].copy(),
            transform=self._window.transform,
            crs=self._window.crs,
            years=list(years),
            group=self._window.group,
        )
