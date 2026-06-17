"""Offline tests for the cube reduction + COG writer (no network/GDAL reads).

The live cube build is exercised by ``spikes/cube_zones``; here we pin the pure
numpy reduction and the GeoTIFF writer, mirroring how ``test_indices.py`` tests
the index kernels without touching COGs.
"""

import numpy as np
from affine import Affine
from rasterio.crs import CRS
from rasterio.io import MemoryFile

from geogent_backend.geo.cube import write_single_band_cog
from geogent_backend.geo.reducers import ReducerName, get_spec

_YEARS = np.array([2023.0, 2024.0, 2025.0])


def test_field_memory_reducer_stability_and_productivity() -> None:
    # 3 dates, 2x2 grid.
    #  - pixel (0,0): constant 0.8       -> high productivity, zero CV (stable)
    #  - pixel (0,1): swings 0.2/0.8/0.2 -> mid productivity, high CV (unstable)
    cube = np.array(
        [
            [[0.8, 0.2], [np.nan, 0.5]],
            [[0.8, 0.8], [np.nan, np.nan]],
            [[0.8, 0.2], [np.nan, 0.5]],
        ],
        dtype="float32",
    )
    out = get_spec(ReducerName.field_memory).reduce(cube, _YEARS, {})
    productivity, stability = out["productivity"], out["stability"]

    assert productivity.shape == (2, 2)
    assert np.isclose(productivity[0, 0], 0.8)
    assert np.isclose(stability[0, 0], 0.0)  # constant -> CV 0
    assert stability[0, 1] > stability[0, 0]  # swinging pixel is less stable
    assert np.isnan(productivity[1, 0])  # all-NaN pixel


def test_trend_reducer_recovers_slope() -> None:
    # A pixel rising 0.2 -> 0.4 -> 0.6 over 2023..2025 has slope +0.2/yr.
    cube = np.array(
        [[[0.2]], [[0.4]], [[0.6]]],
        dtype="float32",
    )
    slope = get_spec(ReducerName.trend).reduce(cube, _YEARS, {})["slope"]
    assert np.isclose(slope[0, 0], 0.2, atol=1e-4)


def test_frequency_reducer_counts_exceedances() -> None:
    # 3 of 4 valid obs exceed 0.3 -> frequency 0.75; NaN ignored.
    cube = np.array(
        [[[0.1]], [[0.4]], [[0.5]], [[0.6]]],
        dtype="float32",
    )
    freq = get_spec(ReducerName.frequency).reduce(cube, np.arange(4.0), {"threshold": 0.3})
    assert np.isclose(freq["frequency"][0, 0], 0.75)


def test_write_single_band_cog_roundtrips() -> None:
    productivity = np.full((8, 8), 0.6, dtype="float32")
    crs = CRS.from_epsg(32611)
    transform = Affine(10.0, 0.0, 500000.0, 0.0, -10.0, 4000000.0)

    data = write_single_band_cog(productivity, crs, transform, "productivity_mean_index")

    assert isinstance(data, bytes) and len(data) > 0
    with MemoryFile(data) as mem, mem.open() as ds:
        assert ds.count == 1
        assert ds.crs.to_epsg() == 32611
        assert np.isclose(ds.read(1).mean(), 0.6, atol=1e-4)
        assert ds.descriptions[0] == "productivity_mean_index"
