"""STAC collection registry (#65 M1.5).

Indices reference *logical* band names (``red``, ``nir``, ``swir22``, …); a
``CollectionSpec`` maps those to a collection's actual STAC asset keys and
carries the DN→reflectance scale/offset so the index kernels always run on
reflectance (Sentinel-2 and Landsat use different scaling). This is what lets
the same cube/reducer machinery span sensors instead of being Sentinel-2 only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from geogent_backend.geo.indices import IndexName, band_keys_for


class CollectionName(str, Enum):  # noqa: UP042 — str-mixin keeps JSON value as the bare string
    sentinel_2_l2a = "sentinel-2-l2a"
    landsat_c2_l2 = "landsat-c2-l2"


@dataclass(frozen=True)
class CollectionSpec:
    stac_id: str
    band_aliases: dict[str, str]  # logical band -> STAC asset key
    cloud_field: str | None  # property for the cloud filter, or None (e.g. SAR)
    scale: float  # DN -> reflectance multiplier
    offset: float  # DN -> reflectance offset
    available: frozenset[str]  # logical bands this sensor provides

    def asset_key(self, logical: str) -> str:
        return self.band_aliases.get(logical, logical)


_S2_BANDS = ("red", "green", "blue", "nir", "rededge1", "swir16", "swir22")
_LANDSAT_BANDS = ("red", "green", "blue", "nir", "swir16", "swir22")

COLLECTIONS: dict[CollectionName, CollectionSpec] = {
    # Earth Search asset keys already match our logical names; DN = reflectance*1e4.
    CollectionName.sentinel_2_l2a: CollectionSpec(
        stac_id="sentinel-2-l2a",
        band_aliases={b: b for b in _S2_BANDS},
        cloud_field="eo:cloud_cover",
        scale=1.0 / 10000.0,
        offset=0.0,
        available=frozenset(_S2_BANDS),
    ),
    # Landsat C2 L2 surface reflectance: nir is "nir08", no red-edge, and a
    # different scale/offset (USGS Collection 2 Level-2 scaling).
    CollectionName.landsat_c2_l2: CollectionSpec(
        stac_id="landsat-c2-l2",
        band_aliases={"nir": "nir08"},
        cloud_field="eo:cloud_cover",
        scale=0.0000275,
        offset=-0.2,
        available=frozenset(_LANDSAT_BANDS),
    ),
}


def get_spec(collection: CollectionName) -> CollectionSpec:
    return COLLECTIONS[collection]


def supports_index(collection: CollectionName, index: IndexName) -> bool:
    spec = COLLECTIONS[collection]
    return all(b in spec.available for b in band_keys_for(index))
