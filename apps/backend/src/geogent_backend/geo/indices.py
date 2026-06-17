"""Spectral index definitions over Sentinel-2 L2A bands.

Each index is described by an :class:`IndexSpec`: the STAC asset keys whose band
COGs it needs, and a pure-numpy compute function that takes those band arrays
(already cast to ``float32``) and returns a float array with ``np.nan`` outside
the valid domain. The registry keeps the math in one place so both the zonal
read path and the offline index tests share exactly the same kernels.

Indices that need 20 m bands (swir16/swir22) or red-edge bands work unchanged:
the read path (``raster.py`` / ``cube.py``) warps every band onto the read
window's grid with ``WarpedVRT`` before calling these kernels, so mixed-
resolution bands are already co-registered here.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum

import numpy as np


class IndexName(str, Enum):  # noqa: UP042 — str-mixin keeps JSON value as the bare string
    ndvi = "ndvi"  # vegetation (red, nir)
    ndwi = "ndwi"  # water — McFeeters (green, nir)
    evi = "evi"  # enhanced vegetation (nir, red, blue)
    nbr = "nbr"  # burn / vegetation health (nir, swir22)
    ndmi = "ndmi"  # vegetation moisture (nir, swir16)
    mndwi = "mndwi"  # modified water — Xu (green, swir16)
    ndre = "ndre"  # red-edge chlorophyll (nir, rededge1)
    savi = "savi"  # soil-adjusted vegetation (nir, red)


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


def _nbr(nir: np.ndarray, swir22: np.ndarray) -> np.ndarray:
    return _normalized_difference(nir, swir22)


def _ndmi(nir: np.ndarray, swir16: np.ndarray) -> np.ndarray:
    return _normalized_difference(nir, swir16)


def _mndwi(green: np.ndarray, swir16: np.ndarray) -> np.ndarray:
    return _normalized_difference(green, swir16)


def _ndre(nir: np.ndarray, rededge1: np.ndarray) -> np.ndarray:
    return _normalized_difference(nir, rededge1)


def _savi(nir: np.ndarray, red: np.ndarray, soil_factor: float = 0.5) -> np.ndarray:
    """Soil-Adjusted Vegetation Index (Huete 1988); ``L=0.5`` reduces soil
    background influence vs NDVI on sparse canopies."""
    denom = nir + red + soil_factor
    return np.where(denom > 0, (nir - red) / denom * (1.0 + soil_factor), np.nan).astype("float32")


# Indices on 20 m (swir16/swir22) or red-edge bands are resampled onto the
# read window's grid by the WarpedVRT path in raster.py / cube.py, so they need
# no special-casing here — the band math is identical to the 10 m ones.
INDICES: dict[IndexName, IndexSpec] = {
    IndexName.ndvi: IndexSpec(band_keys=("red", "nir"), compute=_ndvi),
    IndexName.ndwi: IndexSpec(band_keys=("green", "nir"), compute=_ndwi),
    IndexName.evi: IndexSpec(band_keys=("nir", "red", "blue"), compute=_evi),
    IndexName.nbr: IndexSpec(band_keys=("nir", "swir22"), compute=_nbr),
    IndexName.ndmi: IndexSpec(band_keys=("nir", "swir16"), compute=_ndmi),
    IndexName.mndwi: IndexSpec(band_keys=("green", "swir16"), compute=_mndwi),
    IndexName.ndre: IndexSpec(band_keys=("nir", "rededge1"), compute=_ndre),
    IndexName.savi: IndexSpec(band_keys=("nir", "red"), compute=_savi),
}


def get_spec(index: IndexName) -> IndexSpec:
    return INDICES[index]


def band_keys_for(index: IndexName) -> Sequence[str]:
    return INDICES[index].band_keys
