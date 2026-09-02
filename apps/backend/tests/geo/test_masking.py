"""Offline tests for the per-pixel cloud/shadow masks (#65 M1).

No GDAL/network: the mask specs are pure array predicates, so they're pinned
here the way ``test_indices.py`` pins the index kernels.
"""

import numpy as np
import pytest

from geogent_backend.geo.collections import COLLECTIONS, CollectionName
from geogent_backend.geo.masking import LANDSAT_QA_PIXEL, SENTINEL2_SCL


def test_scl_keeps_vegetation_and_soil_drops_cloud_and_shadow() -> None:
    # SCL classes: 4 vegetation, 5 bare soil, 6 water (all keep);
    # 3 shadow, 8/9 cloud, 10 cirrus, 11 snow (all drop).
    scl = np.array([[4, 5, 6], [3, 9, 10]], dtype="uint8")
    valid = SENTINEL2_SCL.valid(scl)
    assert valid.tolist() == [[True, True, True], [False, False, False]]


def test_scl_drops_nodata_and_saturated() -> None:
    """0 (no data) and 1 (saturated/defective) are not observations either."""
    assert SENTINEL2_SCL.valid(np.array([0, 1, 2, 7], dtype="uint8")).tolist() == [
        False,
        False,
        True,
        True,
    ]


def test_qa_pixel_bitmask_rejects_any_flagged_bit() -> None:
    clear = 0b0000_0000
    cloud = 1 << 3
    shadow = 1 << 4
    cloud_and_shadow = cloud | shadow
    high_confidence_only = 1 << 8  # a bit we deliberately don't gate on
    qa = np.array([clear, cloud, shadow, cloud_and_shadow, high_confidence_only], dtype="uint16")
    assert LANDSAT_QA_PIXEL.valid(qa).tolist() == [True, False, False, False, True]


@pytest.mark.parametrize(
    "collection",
    [CollectionName.sentinel_2_l2a, CollectionName.landsat_c2_l2],
)
def test_every_optical_collection_declares_a_mask(collection: CollectionName) -> None:
    """A sensor with a cloud metric must also carry a per-pixel mask — otherwise
    scene-level filtering silently becomes the only cloud defence."""
    spec = COLLECTIONS[collection]
    assert spec.cloud_field is not None
    assert spec.mask is not None
    assert spec.mask.asset_key


def test_masking_removes_the_fake_instability_cloud_creates() -> None:
    """The reason this module exists: an unmasked cloudy observation inflates
    the temporal CV and reports a steady pixel as unstable."""
    from geogent_backend.geo.reducers import ReducerName, get_spec

    years = np.array([2025.0, 2025.1, 2025.2])
    # A pixel steady at 0.8, but the middle date is cloud (bright, low NDVI).
    unmasked = np.array([[[0.8]], [[0.05]], [[0.8]]], dtype="float32")
    masked = np.array([[[0.8]], [[np.nan]], [[0.8]]], dtype="float32")

    reduce = get_spec(ReducerName.field_memory).reduce
    unstable = reduce(unmasked, years, {})["stability"][0, 0]
    stable = reduce(masked, years, {})["stability"][0, 0]

    assert unstable > 0.5  # reads as wildly erratic ground
    assert np.isclose(stable, 0.0)  # the truth: the pixel never moved
