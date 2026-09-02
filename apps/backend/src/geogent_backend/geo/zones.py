"""Management-zone delineation (#65 M3).

Turns an aligned stack of per-pixel feature layers — typically multi-season
productivity and stability, one pair per index — into a small number of
contiguous agronomic zones, plus the numbers needed to explain *why* each zone
exists.

The pipeline is the standard one, and each step earns its place:

1. **Standardize.** Features are in different units (an NDVI mean near 0.6, a
   CV near 0.15). Without z-scoring, whichever feature has the larger spread
   silently becomes the only thing the clustering sees.
2. **Cluster** with k-means (k-means++ seeding, fixed RNG seed so the same
   field always yields the same map). When ``n_zones`` is None the cluster count
   is chosen by the Calinski-Harabasz index over a small range — a variance-ratio
   criterion that is cheap on 10⁴–10⁵ pixels, unlike silhouette.
3. **Smooth and sieve.** Raw k-means output is per-pixel and speckled; a
   prescription map has to be drivable. A majority filter plus
   ``rasterio.features.sieve`` removes islands too small to manage.
4. **Vectorize** to WGS84 polygons, so the zones can be exported and, later,
   turned into a variable-rate prescription.
5. **Attribute.** For each input feature, the share of its variance explained
   between zones (eta²) says which layer actually drove the split. That is what
   makes the zone map explainable rather than an oracle.

Zones are relabelled by ascending mean of the *first* feature, so "zone 1" is
always the weakest ground and the numbering means the same thing on every field.

Pure numpy + rasterio.features; no sklearn/scipy dependency.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from affine import Affine
from rasterio.crs import CRS
from rasterio.features import shapes, sieve
from rasterio.warp import transform_geom

# Bounds for automatic cluster-count selection. Below 2 there is nothing to
# manage differently; above ~6 the map stops being actionable for a sprayer.
MIN_ZONES = 2
MAX_ZONES = 6

# Clusters are seeded and iterated deterministically: the same field must not
# produce a different zone map on a re-run.
_SEED = 20260615
_MAX_ITERATIONS = 60
_TOLERANCE = 1e-5

# Islands smaller than this are dissolved into their neighbours — a zone you
# cannot steer a machine into is noise, not information.
DEFAULT_MIN_ZONE_PIXELS = 12


class ZoneError(Exception):
    """Zone delineation could not produce a usable map."""


@dataclass(frozen=True)
class FeatureLayer:
    """One ``(y, x)`` input layer, e.g. ``ndvi_productivity``."""

    name: str
    values: np.ndarray


@dataclass(frozen=True)
class ZoneResult:
    labels: np.ndarray  # (y, x) float32, 1-based zone id, NaN outside
    n_zones: int
    zones: list[dict]
    attribution: list[dict]
    n_pixels: int
    selection: list[dict]


def _standardize(matrix: np.ndarray) -> np.ndarray:
    """Z-score each column; a constant column becomes zeros rather than NaN."""
    mean = matrix.mean(axis=0)
    std = matrix.std(axis=0)
    safe = np.where(std > 1e-9, std, 1.0)
    return (matrix - mean) / safe


def _kmeans_plusplus(x: np.ndarray, k: int, rng: np.random.Generator) -> np.ndarray:
    """k-means++ seeding: spread the initial centroids by squared distance."""
    centroids = [x[rng.integers(len(x))]]
    for _ in range(1, k):
        d2 = np.min(
            np.stack([np.sum((x - c) ** 2, axis=1) for c in centroids], axis=0),
            axis=0,
        )
        total = d2.sum()
        if not np.isfinite(total) or total <= 0:
            centroids.append(x[rng.integers(len(x))])
            continue
        centroids.append(x[rng.choice(len(x), p=d2 / total)])
    return np.stack(centroids)


def _kmeans(x: np.ndarray, k: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Lloyd's algorithm. Returns ``(labels, centroids)``."""
    centroids = _kmeans_plusplus(x, k, rng)
    labels = np.zeros(len(x), dtype="int32")
    for _ in range(_MAX_ITERATIONS):
        distances = np.stack([np.sum((x - c) ** 2, axis=1) for c in centroids], axis=1)
        new_labels = np.argmin(distances, axis=1).astype("int32")
        moved = np.empty_like(centroids)
        for j in range(k):
            members = x[new_labels == j]
            # An emptied cluster keeps its centroid rather than becoming NaN.
            moved[j] = members.mean(axis=0) if len(members) else centroids[j]
        shift = float(np.max(np.abs(moved - centroids)))
        centroids, labels = moved, new_labels
        if shift < _TOLERANCE:
            break
    return labels, centroids


def _calinski_harabasz(x: np.ndarray, labels: np.ndarray, k: int) -> float:
    """Variance-ratio criterion: between-cluster dispersion over within-cluster.

    Higher is better. Cheap enough to evaluate for every candidate k on a full
    field, which silhouette (pairwise) would not be.
    """
    n = len(x)
    if k < 2 or n <= k:
        return 0.0
    overall = x.mean(axis=0)
    between = 0.0
    within = 0.0
    for j in range(k):
        members = x[labels == j]
        if len(members) == 0:
            continue
        between += len(members) * float(np.sum((members.mean(axis=0) - overall) ** 2))
        within += float(np.sum((members - members.mean(axis=0)) ** 2))
    if within <= 0:
        return 0.0
    return (between / (k - 1)) / (within / (n - k))


def _majority_filter(labels: np.ndarray, valid: np.ndarray, n_zones: int) -> np.ndarray:
    """3×3 majority vote, counting only valid neighbours (no scipy)."""
    counts = np.zeros((n_zones + 1,) + labels.shape, dtype="int16")
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            shifted = np.roll(np.roll(labels, dy, axis=0), dx, axis=1)
            shifted_valid = np.roll(np.roll(valid, dy, axis=0), dx, axis=1)
            # np.roll wraps; blank the wrapped edge so opposite borders don't vote.
            if dy != 0:
                (shifted_valid[0] if dy > 0 else shifted_valid[-1]).fill(False)
            if dx != 0:
                (shifted_valid[:, 0] if dx > 0 else shifted_valid[:, -1]).fill(False)
            for j in range(1, n_zones + 1):
                counts[j] += (shifted == j) & shifted_valid
    winner = np.argmax(counts[1:], axis=0).astype("int32") + 1
    return np.where(valid, winner, 0).astype("int32")


def _polygons(labels: np.ndarray, valid: np.ndarray, transform: Affine, crs: CRS) -> dict:
    """Vectorize the zone raster into WGS84 MultiPolygons keyed by zone id."""
    by_zone: dict[int, list] = {}
    for geom, value in shapes(labels.astype("int32"), mask=valid, transform=transform):
        zone = int(value)
        if zone <= 0:
            continue
        by_zone.setdefault(zone, []).append(transform_geom(crs, "EPSG:4326", geom))
    return {
        zone: {
            "type": "MultiPolygon",
            "coordinates": [g["coordinates"] for g in geoms if g["type"] == "Polygon"],
        }
        for zone, geoms in by_zone.items()
    }


def _attribution(matrix: np.ndarray, labels: np.ndarray, names: list[str]) -> list[dict]:
    """Per-feature eta²: the share of variance that lies BETWEEN zones.

    ~0 means the zones say nothing about that layer; near 1 means that layer is
    essentially what the zones are. This is the "why" behind the map.
    """
    out = []
    for i, name in enumerate(names):
        column = matrix[:, i]
        total = float(np.sum((column - column.mean()) ** 2))
        if total <= 0:
            out.append({"feature": name, "variance_explained": 0.0})
            continue
        between = 0.0
        for zone in np.unique(labels):
            members = column[labels == zone]
            between += len(members) * float((members.mean() - column.mean()) ** 2)
        out.append({"feature": name, "variance_explained": round(between / total, 4)})
    return sorted(out, key=lambda d: d["variance_explained"], reverse=True)


def delineate(
    features: list[FeatureLayer],
    inside: np.ndarray,
    transform: Affine,
    crs: CRS,
    n_zones: int | None = None,
    min_zone_pixels: int = DEFAULT_MIN_ZONE_PIXELS,
) -> tuple[ZoneResult, dict]:
    """Cluster the feature stack into management zones.

    ``inside`` is the AOI polygon mask. Pixels where any feature is NaN (never
    observed, permanently clouded) are excluded from clustering and end up
    unzoned rather than being imputed.

    Returns ``(result, polygons_by_zone)``. CPU-bound: call via ``to_thread``.
    """
    if not features:
        raise ZoneError("No feature layers to cluster.")

    finite = inside.copy()
    for layer in features:
        finite &= np.isfinite(layer.values)
    n_pixels = int(finite.sum())
    if n_pixels < MAX_ZONES * min_zone_pixels:
        raise ZoneError(
            f"Only {n_pixels} usable pixels inside the area — too few to delineate zones. "
            "Use a larger field, a longer date range, or a cloudier-tolerant window."
        )

    names = [layer.name for layer in features]
    matrix = np.stack([layer.values[finite] for layer in features], axis=1).astype("float64")
    scaled = _standardize(matrix)
    rng = np.random.default_rng(_SEED)

    # Cluster-count selection: either the caller's k, or the best variance ratio
    # over the allowed range. The scores are returned so the agent can say how
    # clear-cut the choice was.
    selection: list[dict] = []
    if n_zones is None:
        best: tuple[float, int, np.ndarray] | None = None
        for k in range(MIN_ZONES, min(MAX_ZONES, n_pixels - 1) + 1):
            labels_k, _ = _kmeans(scaled, k, np.random.default_rng(_SEED))
            score = _calinski_harabasz(scaled, labels_k, k)
            selection.append({"n_zones": k, "score": round(score, 2)})
            if best is None or score > best[0]:
                best = (score, k, labels_k)
        if best is None:
            raise ZoneError("Cluster-count selection failed.")
        _, chosen_k, flat_labels = best
    else:
        chosen_k = max(MIN_ZONES, min(int(n_zones), MAX_ZONES))
        flat_labels, _ = _kmeans(scaled, chosen_k, rng)

    # Relabel by ascending mean of the primary feature so zone 1 is always the
    # weakest ground — the numbering has to mean the same thing on every field.
    primary = matrix[:, 0]
    order = np.argsort([primary[flat_labels == j].mean() for j in range(chosen_k)])
    remap = np.zeros(chosen_k, dtype="int32")
    for rank, cluster in enumerate(order, start=1):
        remap[cluster] = rank
    flat_labels = remap[flat_labels]

    raster = np.zeros(inside.shape, dtype="int32")
    raster[finite] = flat_labels
    raster = _majority_filter(raster, finite, chosen_k)
    raster = sieve(raster, size=min_zone_pixels, mask=finite)
    raster = np.where(finite, raster, 0).astype("int32")

    # Smoothing/sieving moved pixels, so the reported stats are recomputed from
    # the final raster rather than from the pre-smoothing cluster assignment.
    final_flat = raster[finite]
    polygons = _polygons(raster, finite, transform, crs)

    pixel_area_ha = abs(transform.a * transform.e) / 10_000.0
    zones: list[dict] = []
    for zone in range(1, chosen_k + 1):
        members = final_flat == zone
        count = int(members.sum())
        if count == 0:
            continue
        zones.append(
            {
                "zone": zone,
                "pixels": count,
                "area_ha": round(count * pixel_area_ha, 3),
                "share_of_area": round(count / max(n_pixels, 1), 4),
                "features": {
                    name: round(float(matrix[members, i].mean()), 4) for i, name in enumerate(names)
                },
            }
        )

    return (
        ZoneResult(
            labels=np.where(finite, raster, np.nan).astype("float32"),
            n_zones=len(zones),
            zones=zones,
            attribution=_attribution(matrix, final_flat, names),
            n_pixels=n_pixels,
            selection=selection,
        ),
        polygons,
    )
