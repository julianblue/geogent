"""Per-pixel cloud / shadow / snow masking (#65 M1).

Every index statistic in this codebase is computed over a *polygon*, so a scene
that passes a scene-level ``eo:cloud_cover`` filter can still put cloud or
shadow directly on the field. Left unmasked those pixels do real damage:

- a single shadowed corner drags a zonal mean down and gets read as stress;
- in a temporal cube, cloud/shadow swings inflate the temporal standard
  deviation and therefore the ``stability`` layer, manufacturing "instability"
  where the ground was in fact steady. That is the failure mode this module
  exists to remove.

Both sensors we support ship a per-pixel quality band, but in different shapes —
Sentinel-2 a *classification* raster (SCL), Landsat a *bit-packed* QA raster —
so a :class:`MaskSpec` describes which asset to read and how to turn it into a
boolean "this pixel is usable" array. The read paths (``raster.py``,
``cube.py``) warp that band onto the same canonical grid as the spectral bands,
so a 20 m SCL lines up with 10 m reflectance without special-casing.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np


class MaskKind(str, Enum):  # noqa: UP042 — str-mixin keeps JSON value as the bare string
    classes = "classes"  # value-per-class raster (Sentinel-2 SCL)
    bits = "bits"  # bit-packed QA raster (Landsat QA_PIXEL)


@dataclass(frozen=True)
class MaskSpec:
    """How to derive a validity mask from a collection's quality band.

    ``values`` is read according to ``kind``: for ``classes`` it is the set of
    class values to REJECT; for ``bits`` it is the set of bit positions where a
    set bit means REJECT.
    """

    asset_key: str
    kind: MaskKind
    values: frozenset[int]
    label: str

    def valid(self, qa: np.ndarray) -> np.ndarray:
        """``(y, x)`` boolean array — True where the pixel is usable."""
        codes = qa.astype("int64", copy=False)
        if self.kind is MaskKind.classes:
            return ~np.isin(codes, list(self.values))
        reject = 0
        for bit in self.values:
            reject |= 1 << bit
        return (codes & reject) == 0


# Sentinel-2 L2A Scene Classification Layer. 3/8/9/10 are the shadow+cloud
# classes the roadmap calls out; 11 (snow/ice) is spectrally indistinguishable
# from bright cloud for index purposes; 0 (no data) and 1 (saturated/defective)
# are not real observations either. Kept classes: 2 dark area, 4 vegetation,
# 5 bare soil, 6 water, 7 unclassified — 4 and 5 are the agronomically
# interesting ones and must never be dropped.
SENTINEL2_SCL = MaskSpec(
    asset_key="scl",
    kind=MaskKind.classes,
    values=frozenset({0, 1, 3, 8, 9, 10, 11}),
    label="Sentinel-2 SCL (no-data, saturated, shadow, cloud, cirrus, snow)",
)

# Landsat Collection-2 QA_PIXEL bit flags: 0 fill, 1 dilated cloud, 2 cirrus,
# 3 cloud, 4 cloud shadow, 5 snow. (Bits 6+ are clear/water and confidence
# pairs, which we don't gate on.)
LANDSAT_QA_PIXEL = MaskSpec(
    asset_key="qa_pixel",
    kind=MaskKind.bits,
    values=frozenset({0, 1, 2, 3, 4, 5}),
    label="Landsat QA_PIXEL (fill, dilated cloud, cirrus, cloud, shadow, snow)",
)
