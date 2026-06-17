"""Offline tests for the cube reduction + COG writer (no network/GDAL reads).

The live cube build is exercised by ``spikes/cube_zones``; here we pin the pure
numpy reduction and the GeoTIFF writer, mirroring how ``test_indices.py`` tests
the index kernels without touching COGs.
"""

import numpy as np
from affine import Affine
from rasterio.crs import CRS
from rasterio.io import MemoryFile

from geogent_backend.geo.cube import reduce_field_memory, write_single_band_cog


def test_reduce_field_memory_stability_and_productivity() -> None:
    # 3 dates, 2x2 grid.
    #  - pixel (0,0): constant 0.8       -> high productivity, zero CV (stable)
    #  - pixel (0,1): swings 0.2/0.8/0.2 -> mid productivity, high CV (unstable)
    #  - pixel (1,0): all NaN            -> no obs
    #  - pixel (1,1): two obs + one NaN  -> counted as 2 obs
    cube = np.array(
        [
            [[0.8, 0.2], [np.nan, 0.5]],
            [[0.8, 0.8], [np.nan, np.nan]],
            [[0.8, 0.2], [np.nan, 0.5]],
        ],
        dtype="float32",
    )
    productivity, stability, n_obs = reduce_field_memory(cube)

    assert productivity.shape == (2, 2)
    assert np.isclose(productivity[0, 0], 0.8)
    assert np.isclose(stability[0, 0], 0.0)  # constant -> CV 0
    assert stability[0, 1] > stability[0, 0]  # swinging pixel is less stable
    assert n_obs[0, 0] == 3
    assert n_obs[1, 0] == 0  # all-NaN pixel
    assert n_obs[1, 1] == 2
    assert np.isnan(productivity[1, 0])


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
