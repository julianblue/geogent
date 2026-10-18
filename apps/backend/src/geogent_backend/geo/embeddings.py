"""Field-level maths on TESSERA embedding windows (ADR 0003): pure numpy.

Ported from ``spikes/tessera_embeddings/poc_field_embeddings.py`` (field masking,
per-field per-year stats, AOI-mean centring, year-over-year cosine distance) and
``poc_tessera_read.py`` (PCA false colour). No store access — the reader hands in
``(band, y, x)`` float32 arrays with NaN where a pixel was not embedded, and every
function here treats a pixel as usable only if **all** its bands are finite, so a
NaN can never leak into a mean, a centred distance or a PCA fit.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from affine import Affine
from rasterio.features import rasterize
from shapely.geometry.base import BaseGeometry

# Fields with fewer usable interior pixels than this are flagged unusable.
MIN_FIELD_PIXELS = 5
# One 10 m pixel: keeps edge (mixed) pixels out of the field statistics.
INWARD_BUFFER_M = 10.0


def finite_pixels(emb: np.ndarray) -> np.ndarray:
    """``(band, y, x)`` → ``(y, x)`` bool: every band of the pixel is finite."""
    return np.isfinite(emb).all(axis=0)


# --------------------------------------------------------------------------- field mask


def rasterize_mask(geom: BaseGeometry, shape: tuple[int, int], transform: Affine) -> np.ndarray:
    """Pixels whose centre lies inside ``geom`` (projected into the grid's CRS)."""
    if geom is None or geom.is_empty:
        return np.zeros(shape, dtype=bool)
    out = rasterize([(geom, 1)], out_shape=shape, transform=transform, fill=0, dtype="uint8")
    return out.astype(bool)


def field_mask(
    geom_proj: BaseGeometry,
    shape: tuple[int, int],
    transform: Affine,
    buffer_m: float = INWARD_BUFFER_M,
) -> tuple[np.ndarray, bool]:
    """Boolean ``(y, x)`` mask of the field's interior pixels.

    The geometry is shrunk by ``buffer_m`` first; if that leaves nothing the
    unbuffered polygon is used instead. Returns ``(mask, buffered)``. The mask is
    purely geometric — NaN (non-embedded) pixels are removed per year by the
    stats functions, so one mask serves every year."""
    if buffer_m > 0:
        mask = rasterize_mask(geom_proj.buffer(-buffer_m), shape, transform)
        if mask.any():
            return mask, True
    return rasterize_mask(geom_proj, shape, transform), False


# --------------------------------------------------------------------------- stats


@dataclass
class YearStats:
    """Field statistics for one year. ``mean``/``std`` are NaN when no pixel is usable."""

    pixel_count: int
    masked_fraction: float  # share of the field's pixels that had no embedding
    mean: np.ndarray  # (band,)
    std: np.ndarray  # (band,)
    heterogeneity: float  # mean cosine distance of the pixels to the field mean; NaN if none

    @property
    def usable(self) -> bool:
        return self.pixel_count >= MIN_FIELD_PIXELS


def cosine_distance(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """``1 - cos`` along the last axis; NaN where either vector is NaN or zero-length."""
    dot = (a * b).sum(axis=-1)
    den = np.linalg.norm(a, axis=-1) * np.linalg.norm(b, axis=-1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return 1.0 - dot / den


def year_stats(emb_year: np.ndarray, mask: np.ndarray) -> YearStats:
    """Mean / std / pixel count of ``emb_year`` ``(band, y, x)`` over ``mask``,
    restricted to the finite pixels *before* any threshold is applied."""
    n_band = emb_year.shape[0]
    in_field = int(mask.sum())
    sel = mask & finite_pixels(emb_year)
    n = int(sel.sum())
    masked_fraction = 1.0 - n / in_field if in_field else 1.0
    if n == 0:
        nan = np.full(n_band, np.nan, dtype=np.float64)
        return YearStats(0, masked_fraction, nan, nan.copy(), float("nan"))
    px = emb_year[:, sel].T.astype(np.float64)  # (pixels, band)
    mean = px.mean(axis=0)
    het = cosine_distance(px, mean[None, :]).mean()
    return YearStats(n, masked_fraction, mean, px.std(axis=0), float(het))


def window_mean(emb_year: np.ndarray) -> tuple[np.ndarray, int]:
    """Mean embedding over the finite pixels of a whole window, plus their count —
    the per-year offset that centring removes. NaN vector when nothing is finite."""
    ok = finite_pixels(emb_year)
    n = int(ok.sum())
    if n == 0:
        return np.full(emb_year.shape[0], np.nan, dtype=np.float64), 0
    # band by band: avoids materialising a (band, pixels) copy of a large window
    return np.array([emb_year[b][ok].mean(dtype=np.float64) for b in range(emb_year.shape[0])]), n


def yoy_distance(
    mean_a: np.ndarray, mean_b: np.ndarray, offset_a: np.ndarray, offset_b: np.ndarray
) -> tuple[float, float]:
    """``(centred, raw)`` cosine distance between two field-mean embeddings.

    Centring subtracts each year's own AOI-window mean first: the raw distance
    carries a large global year-to-year offset (~0.24 for every pair in the
    spike), which the centred one removes (rotation AUC 0.84 raw -> 0.90)."""
    raw = float(cosine_distance(mean_a, mean_b))
    centred = float(cosine_distance(mean_a - offset_a, mean_b - offset_b))
    return centred, raw


# --------------------------------------------------------------------------- PCA


def pca_rgb(emb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """PCA(3) false colour of one ``(band, y, x)`` window.

    The PCA is fit on the finite pixels only. Each component is stretched
    p2–p98 to **1..255** so that 0 can serve as GeoTIFF nodata (every non-finite
    pixel is 0 in all three bands). Returns ``(uint8 (3, y, x), valid (y, x),
    explained_variance_ratio (3,))``. Component signs are fixed (largest loading
    positive) so a run is deterministic, but they stay arbitrary across layers —
    colours are NOT comparable between years. With fewer than 3 bands the missing
    components are flat mid-grey with ratio 0."""
    n_band, h, w = emb.shape
    valid = finite_pixels(emb)
    out = np.zeros((3, h * w), dtype=np.uint8)
    ratio = np.zeros(3, dtype=np.float64)
    flat_valid = valid.reshape(-1)
    n = int(flat_valid.sum())
    if n < 2:
        out[:, flat_valid] = 128  # a lone valid pixel has no contrast, but must not read as nodata
        return out.reshape(3, h, w), valid, ratio

    x = np.ascontiguousarray(emb.reshape(n_band, -1)[:, flat_valid].T, dtype=np.float32)
    x -= x.mean(axis=0)
    cov = (x.T @ x) / np.float32(n - 1)
    eigval, eigvec = np.linalg.eigh(cov)
    order = np.argsort(eigval)[::-1][: min(3, n_band)]
    vecs = eigvec[:, order]
    flip = np.sign(vecs[np.abs(vecs).argmax(axis=0), np.arange(vecs.shape[1])])
    vecs = vecs * np.where(flip == 0, 1.0, flip).astype(vecs.dtype)
    scores = x @ vecs  # (pixels, k) float32
    total = float(eigval.clip(min=0).sum())
    if total > 0:
        ratio[: len(order)] = eigval[order].clip(min=0) / total

    for i in range(3):
        if i >= scores.shape[1]:
            out[i, flat_valid] = 128
            continue
        lo, hi = np.percentile(scores[:, i], [2, 98])
        if hi <= lo:  # constant component: no contrast to stretch
            out[i, flat_valid] = 128
            continue
        scaled = np.clip((scores[:, i] - lo) / (hi - lo), 0.0, 1.0)
        out[i, flat_valid] = (1 + scaled * 254).astype(np.uint8)
    return out.reshape(3, h, w), valid, ratio
