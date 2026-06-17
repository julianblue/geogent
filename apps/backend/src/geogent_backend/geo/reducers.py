"""Per-pixel temporal reducers over a data cube.

A reducer collapses the time axis of a ``(time, y, x)`` index cube into one or
more ``(y, x)`` output layers. This is the pluggable family that turns the cube
from "field memory only" into a general temporal-raster engine (ADR 0002, M1.5):
each reducer is a pure numpy function + an output spec, and the
cube/artifact/render scaffolding around it is reused unchanged.

Each output declares a ``colormap`` id; the UI maps that id to a GLSL ramp, so
adding a reducer needs no bespoke UI wiring (just a colormap the UI already
knows, or one new ramp).
"""

from __future__ import annotations

import warnings
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

import numpy as np


class ReducerName(str, Enum):  # noqa: UP042 — str-mixin keeps JSON value as the bare string
    field_memory = "field_memory"
    composite = "composite"
    trend = "trend"
    frequency = "frequency"


@dataclass(frozen=True)
class ReducerOutput:
    """One ``(y, x)`` layer a reducer produces. ``name`` is the asset role."""

    name: str
    label: str
    colormap: str  # UI colormap id (see apps/ui raster-modules COLORMAP_MODULES)


@dataclass(frozen=True)
class ReducerSpec:
    outputs: tuple[ReducerOutput, ...]
    # (cube, years, params) -> {output_name: (y, x) float array, NaN = nodata}
    reduce: Callable[[np.ndarray, np.ndarray, dict], dict[str, np.ndarray]]


def _suppress_allnan():
    # All-NaN pixels (outside polygon / fully masked) warn on nanmean/nanstd;
    # expected — callers mask them out via the polygon + valid-obs count.
    w = warnings.catch_warnings()
    warnings.simplefilter("ignore", category=RuntimeWarning)
    return w


def _field_memory(cube: np.ndarray, _years: np.ndarray, _params: dict) -> dict[str, np.ndarray]:
    with _suppress_allnan():
        productivity = np.nanmean(cube, axis=0).astype("float32")
        tstd = np.nanstd(cube, axis=0).astype("float32")
    stability = np.where(productivity > 0, tstd / productivity, np.nan).astype("float32")
    return {"productivity": productivity, "stability": stability}


def _composite(cube: np.ndarray, _years: np.ndarray, _params: dict) -> dict[str, np.ndarray]:
    with _suppress_allnan():
        median = np.nanmedian(cube, axis=0).astype("float32")
    return {"composite": median}


def _trend(cube: np.ndarray, years: np.ndarray, _params: dict) -> dict[str, np.ndarray]:
    """Per-pixel OLS slope of the index vs. time (index units per year).

    Vectorized masked least-squares: NaN observations are dropped per pixel, and
    pixels with fewer than two valid samples (or no time spread) yield NaN.
    """
    mask = np.isfinite(cube)
    x = years[:, None, None] * mask  # zero where masked
    y = np.where(mask, cube, 0.0)
    n = mask.sum(axis=0)
    sx = x.sum(axis=0)
    sy = y.sum(axis=0)
    sxx = (x * x).sum(axis=0)
    sxy = (x * y).sum(axis=0)
    denom = n * sxx - sx * sx
    with np.errstate(invalid="ignore", divide="ignore"):
        slope = np.where(denom > 0, (n * sxy - sx * sy) / denom, np.nan)
    slope = np.where(n >= 2, slope, np.nan).astype("float32")
    return {"slope": slope}


def _frequency(cube: np.ndarray, _years: np.ndarray, params: dict) -> dict[str, np.ndarray]:
    """Fraction of valid observations where the index exceeds ``threshold``."""
    threshold = float(params.get("threshold", 0.3))
    valid = np.isfinite(cube)
    above = (cube > threshold) & valid
    n = valid.sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        freq = np.where(n > 0, above.sum(axis=0) / n, np.nan)
    return {"frequency": freq.astype("float32")}


REDUCERS: dict[ReducerName, ReducerSpec] = {
    ReducerName.field_memory: ReducerSpec(
        outputs=(
            ReducerOutput("productivity", "Productivity (mean)", "rdylgn"),
            ReducerOutput("stability", "Stability (temporal CV)", "stability"),
        ),
        reduce=_field_memory,
    ),
    ReducerName.composite: ReducerSpec(
        outputs=(ReducerOutput("composite", "Median composite", "rdylgn"),),
        reduce=_composite,
    ),
    ReducerName.trend: ReducerSpec(
        outputs=(ReducerOutput("slope", "Trend (per year)", "diverging"),),
        reduce=_trend,
    ),
    ReducerName.frequency: ReducerSpec(
        outputs=(ReducerOutput("frequency", "Frequency above threshold", "sequential"),),
        reduce=_frequency,
    ),
}


def get_spec(reducer: ReducerName) -> ReducerSpec:
    return REDUCERS[reducer]
