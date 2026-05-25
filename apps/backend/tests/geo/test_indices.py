"""Offline index-math tests on a synthetic in-memory raster.

No network: we hand-build small red/nir/green/blue arrays over a grid that
straddles the Ames, Iowa fixture polygon, run the same ``geometry_mask`` +
index kernels the production read path uses, and assert the values against
hand-computed expectations (and that masking excludes pixels outside the
polygon).
"""

from __future__ import annotations

import numpy as np
import pytest
from rasterio.features import geometry_mask
from rasterio.transform import from_origin

from geogent_backend.geo.indices import IndexName, get_spec

# A real ~5 ha rectangular field near Ames, Iowa (lon/lat, SRID 4326), copied
# from tests/api/test_fields.py.
FIXTURE_POLYGON = {
    "type": "Polygon",
    "coordinates": [
        [
            [-93.650, 42.020],
            [-93.647, 42.020],
            [-93.647, 42.022],
            [-93.650, 42.022],
            [-93.650, 42.020],
        ]
    ],
}

# A 4x4 grid of 0.001-degree pixels whose interior straddles the polygon.
# Origin (top-left) is northwest of the polygon so some pixels fall outside it.
_PIXEL = 0.001
_ORIGIN_LON = -93.651
_ORIGIN_LAT = 42.023
_TRANSFORM = from_origin(_ORIGIN_LON, _ORIGIN_LAT, _PIXEL, _PIXEL)
_SHAPE = (4, 4)


def _polygon_mask() -> np.ndarray:
    """True inside the polygon (invert=True), matching the production path."""
    return geometry_mask(
        [FIXTURE_POLYGON],
        out_shape=_SHAPE,
        transform=_TRANSFORM,
        invert=True,
    )


def test_mask_excludes_pixels_outside_polygon() -> None:
    mask = _polygon_mask()
    # Not everything is inside (the grid extends past the polygon) and at least
    # some cells are inside.
    assert mask.any()
    assert not mask.all()


def test_ndvi_matches_hand_computation() -> None:
    red = np.full(_SHAPE, 2000.0, dtype="float32")
    nir = np.full(_SHAPE, 6000.0, dtype="float32")
    values = get_spec(IndexName.ndvi).compute(red, nir)
    # NDVI = (nir - red) / (nir + red) = 4000 / 8000 = 0.5
    expected = (6000.0 - 2000.0) / (6000.0 + 2000.0)
    assert np.allclose(values, expected)


def test_ndwi_matches_hand_computation() -> None:
    green = np.full(_SHAPE, 3000.0, dtype="float32")
    nir = np.full(_SHAPE, 1000.0, dtype="float32")
    values = get_spec(IndexName.ndwi).compute(green, nir)
    # NDWI = (green - nir) / (green + nir) = 2000 / 4000 = 0.5
    expected = (3000.0 - 1000.0) / (3000.0 + 1000.0)
    assert np.allclose(values, expected)


def test_evi_matches_hand_computation() -> None:
    nir = np.full(_SHAPE, 3000.0, dtype="float32")
    red = np.full(_SHAPE, 1000.0, dtype="float32")
    blue = np.full(_SHAPE, 500.0, dtype="float32")
    values = get_spec(IndexName.evi).compute(nir, red, blue)
    # Reflectance-scaled (/10000): nir=0.3 red=0.1 blue=0.05
    n, r, b = 0.3, 0.1, 0.05
    expected = 2.5 * (n - r) / (n + 6.0 * r - 7.5 * b + 1.0)
    assert np.allclose(values, expected, atol=1e-5)


def test_normalized_difference_guards_zero_denominator() -> None:
    red = np.zeros(_SHAPE, dtype="float32")
    nir = np.zeros(_SHAPE, dtype="float32")
    values = get_spec(IndexName.ndvi).compute(red, nir)
    assert np.isnan(values).all()


def test_masked_reduction_only_counts_inside_pixels() -> None:
    """End-to-end: index over the window, masked to polygon, reduced with numpy."""
    red = np.full(_SHAPE, 2000.0, dtype="float32")
    nir = np.full(_SHAPE, 6000.0, dtype="float32")
    # Make pixels OUTSIDE the polygon obviously different so they'd skew the
    # mean if the mask leaked.
    mask = _polygon_mask()
    nir[~mask] = 9999.0

    values = get_spec(IndexName.ndvi).compute(red, nir)
    inside = values[mask]
    finite = inside[np.isfinite(inside)]
    assert finite.size > 0
    # All inside pixels share the 0.5 NDVI; the outside (9999) pixels are excluded.
    assert np.allclose(np.mean(finite), 0.5)


def test_nbr_is_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        get_spec(IndexName.nbr).compute(
            np.zeros(_SHAPE, dtype="float32"), np.zeros(_SHAPE, dtype="float32")
        )
