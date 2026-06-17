"""Collection registry: band aliasing + per-sensor index availability (#65)."""

from geogent_backend.geo.collections import CollectionName, get_spec, supports_index
from geogent_backend.geo.indices import IndexName


def test_band_aliases_map_logical_to_asset_keys() -> None:
    s2 = get_spec(CollectionName.sentinel_2_l2a)
    landsat = get_spec(CollectionName.landsat_c2_l2)
    # Sentinel-2 asset keys equal the logical names; Landsat renames nir -> nir08.
    assert s2.asset_key("nir") == "nir"
    assert landsat.asset_key("nir") == "nir08"
    assert landsat.asset_key("red") == "red"


def test_reflectance_scaling_differs_by_sensor() -> None:
    assert get_spec(CollectionName.sentinel_2_l2a).offset == 0.0
    assert get_spec(CollectionName.landsat_c2_l2).offset != 0.0


def test_index_availability_per_collection() -> None:
    # NDVI is available on both; NDRE needs red-edge, which Landsat lacks.
    assert supports_index(CollectionName.sentinel_2_l2a, IndexName.ndvi)
    assert supports_index(CollectionName.landsat_c2_l2, IndexName.ndvi)
    assert supports_index(CollectionName.sentinel_2_l2a, IndexName.ndre)
    assert not supports_index(CollectionName.landsat_c2_l2, IndexName.ndre)
