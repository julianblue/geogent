"""Spectral index definitions over Sentinel-2 L2A bands.

Each index is described by an :class:`IndexSpec`: the STAC asset keys whose band
COGs it needs, and a pure-numpy compute function that takes those band arrays
(already cast to ``float32``) and returns a float array with ``np.nan`` outside
the valid domain. The registry keeps the math in one place so both the zonal
read path and the offline index tests share exactly the same kernels.

All supported indices use 10 m bands (red/green/blue/nir), so they share one
pixel grid and need no resampling. ``nbr`` is reserved but not yet implemented:
it requires the 20 m swir22 band resampled onto the 10 m grid.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum

import numpy as np


class IndexName(str, Enum):  # noqa: UP042 — str-mixin keeps JSON value as the bare string
    ndvi = "ndvi"
    ndwi = "ndwi"
    evi = "evi"
    nbr = "nbr"


@dataclass(frozen=True)
class IndexSpec:
    """A spectral index: the band asset keys it reads and how to compute it.

    ``compute`` receives the band arrays as ``float32`` ndarrays in the same
    order as ``band_keys`` and returns a float array (np.nan where undefined).
    """

    band_keys: tuple[str, ...]
    compute: Callable[..., np.ndarray]


def _normalized_difference(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """``(a - b) / (a + b)`` with np.nan where the denominator is not positive."""
    denom = a + b
    return np.where(denom > 0, (a - b) / denom, np.nan).astype("float32")


def _ndvi(red: np.ndarray, nir: np.ndarray) -> np.ndarray:
    return _normalized_difference(nir, red)


def _ndwi(green: np.ndarray, nir: np.ndarray) -> np.ndarray:
    return _normalized_difference(green, nir)


def _evi(nir: np.ndarray, red: np.ndarray, blue: np.ndarray) -> np.ndarray:
    """Enhanced Vegetation Index on reflectance-scaled (0..1) band values.

    Sentinel-2 L2A digital numbers are reflectance * 10000; scale them down so
    the EVI constants (the +1 and the 6/-7.5 coefficients) are dimensionally
    correct.
    """
    nir_r = nir / 10000.0
    red_r = red / 10000.0
    blue_r = blue / 10000.0
    denom = nir_r + 6.0 * red_r - 7.5 * blue_r + 1.0
    return np.where(denom != 0, 2.5 * (nir_r - red_r) / denom, np.nan).astype("float32")


def _nbr_not_implemented(*_bands: np.ndarray) -> np.ndarray:
    # TODO: NBR needs the 20 m swir22 band resampled onto the 10 m grid before
    # it can share the single-window read path used by the other indices.
    raise NotImplementedError(
        "NBR is not implemented yet: it requires the 20 m swir22 band resampled onto the 10 m grid."
    )


INDICES: dict[IndexName, IndexSpec] = {
    IndexName.ndvi: IndexSpec(band_keys=("red", "nir"), compute=_ndvi),
    IndexName.ndwi: IndexSpec(band_keys=("green", "nir"), compute=_ndwi),
    IndexName.evi: IndexSpec(band_keys=("nir", "red", "blue"), compute=_evi),
    IndexName.nbr: IndexSpec(band_keys=("nir", "swir22"), compute=_nbr_not_implemented),
}


def get_spec(index: IndexName) -> IndexSpec:
    return INDICES[index]


def band_keys_for(index: IndexName) -> Sequence[str]:
    return INDICES[index].band_keys
