"""Offline tests for management-zone delineation (#65 M3).

Synthetic fields with a *known* structure — a planted gradient, a two-patch
split, a uniform field — so the assertions are about whether the pipeline
recovers the truth, not about exact cluster ids.
"""

import numpy as np
import pytest
from affine import Affine
from rasterio.crs import CRS

from geogent_backend.geo.zones import FeatureLayer, ZoneError, delineate

# 10 m pixels in a projected CRS, origin at a round UTM-ish coordinate.
TRANSFORM = Affine(10.0, 0.0, 400_000.0, 0.0, -10.0, 5_900_000.0)
CRS_32633 = CRS.from_epsg(32633)


def _inside(shape: tuple[int, int]) -> np.ndarray:
    return np.ones(shape, dtype=bool)


def test_two_patch_field_splits_into_two_zones() -> None:
    """A field that is genuinely two halves must come back as two zones, with
    the weak half labelled 1."""
    productivity = np.zeros((40, 40), dtype="float32")
    productivity[:, :20] = 0.30  # weak half
    productivity[:, 20:] = 0.75  # strong half
    productivity += np.random.default_rng(1).normal(0, 0.01, productivity.shape)

    result, polygons = delineate(
        [FeatureLayer("ndvi_productivity", productivity)],
        _inside(productivity.shape),
        TRANSFORM,
        CRS_32633,
        n_zones=2,
    )

    assert result.n_zones == 2
    weak, strong = result.zones[0], result.zones[1]
    assert weak["zone"] == 1
    # Zone 1 is the low-productivity half — the labelling contract.
    assert weak["features"]["ndvi_productivity"] < strong["features"]["ndvi_productivity"]
    assert abs(weak["share_of_area"] - 0.5) < 0.05
    assert set(polygons) == {1, 2}
    assert polygons[1]["type"] == "MultiPolygon"


def test_zone_areas_use_the_pixel_size() -> None:
    productivity = np.zeros((40, 40), dtype="float32")
    productivity[:, :20] = 0.3
    productivity[:, 20:] = 0.8

    result, _ = delineate(
        [FeatureLayer("p", productivity)], _inside(productivity.shape), TRANSFORM, CRS_32633, 2
    )

    # 800 pixels of 10x10 m = 8 ha per half.
    assert all(abs(z["area_ha"] - 8.0) < 0.5 for z in result.zones)


def test_attribution_names_the_layer_that_actually_split_the_field() -> None:
    """Zones driven by productivity must attribute to productivity, not to a
    noise layer that happens to be in the stack."""
    rng = np.random.default_rng(7)
    productivity = np.where(np.arange(40)[None, :] < 20, 0.3, 0.8) * np.ones((40, 40))
    noise = rng.normal(0.2, 0.02, (40, 40))

    result, _ = delineate(
        [
            FeatureLayer("ndvi_productivity", productivity.astype("float32")),
            FeatureLayer("ndvi_stability", noise.astype("float32")),
        ],
        _inside(productivity.shape),
        TRANSFORM,
        CRS_32633,
        n_zones=2,
    )

    top = result.attribution[0]
    assert top["feature"] == "ndvi_productivity"
    assert top["variance_explained"] > 0.9
    assert result.attribution[1]["variance_explained"] < 0.2


def test_auto_zone_count_prefers_the_planted_structure() -> None:
    """Three clearly separated levels should not be forced into two zones."""
    field = np.zeros((45, 45), dtype="float32")
    field[:15] = 0.25
    field[15:30] = 0.55
    field[30:] = 0.85
    field += np.random.default_rng(3).normal(0, 0.005, field.shape)

    result, _ = delineate(
        [FeatureLayer("p", field)], _inside(field.shape), TRANSFORM, CRS_32633, n_zones=None
    )

    assert result.n_zones == 3
    means = [z["features"]["p"] for z in result.zones]
    assert means == sorted(means)  # ascending by construction
    assert {s["n_zones"] for s in result.selection} == {2, 3, 4, 5, 6}


def test_uniform_field_reports_near_zero_attribution() -> None:
    """A field with no real structure still returns a map (the caller asked for
    one) but nothing explains it — that is the signal not to act on it."""
    field = np.full((40, 40), 0.6, dtype="float32")
    field += np.random.default_rng(5).normal(0, 0.001, field.shape)

    result, _ = delineate(
        [FeatureLayer("p", field)], _inside(field.shape), TRANSFORM, CRS_32633, n_zones=2
    )

    # Splitting pure noise: the zones exist but the field is not really divided.
    spread = abs(result.zones[0]["features"]["p"] - result.zones[-1]["features"]["p"])
    assert spread < 0.01


def test_unobserved_pixels_are_excluded_not_imputed() -> None:
    field = np.zeros((40, 40), dtype="float32")
    field[:, :20] = 0.3
    field[:, 20:] = 0.8
    field[0:5, 0:5] = np.nan  # never observed (permanent cloud)

    result, _ = delineate(
        [FeatureLayer("p", field)], _inside(field.shape), TRANSFORM, CRS_32633, n_zones=2
    )

    assert result.n_pixels == 40 * 40 - 25
    assert np.isnan(result.labels[0, 0])  # stays unzoned
    assert not np.isnan(result.labels[39, 39])


def test_a_field_too_small_to_zone_raises_rather_than_guessing() -> None:
    tiny = np.full((4, 4), 0.5, dtype="float32")

    with pytest.raises(ZoneError, match="too few to delineate"):
        delineate([FeatureLayer("p", tiny)], _inside(tiny.shape), TRANSFORM, CRS_32633)


def test_delineation_is_deterministic() -> None:
    """The same field must produce the same map twice — a prescription that
    changes on re-run is unusable."""
    rng = np.random.default_rng(11)
    field = (rng.normal(0.5, 0.15, (40, 40))).astype("float32")

    a, _ = delineate([FeatureLayer("p", field)], _inside(field.shape), TRANSFORM, CRS_32633, 3)
    b, _ = delineate([FeatureLayer("p", field)], _inside(field.shape), TRANSFORM, CRS_32633, 3)

    np.testing.assert_array_equal(np.nan_to_num(a.labels, nan=-1), np.nan_to_num(b.labels, nan=-1))


def test_speckle_is_removed_by_smoothing_and_sieving() -> None:
    """Isolated single pixels of the wrong class must not survive into the map."""
    field = np.full((40, 40), 0.8, dtype="float32")
    field[:, :20] = 0.3
    # Salt a handful of single stray pixels into the strong half.
    for y, x in [(5, 30), (12, 33), (25, 27), (31, 36)]:
        field[y, x] = 0.3

    result, _ = delineate(
        [FeatureLayer("p", field)], _inside(field.shape), TRANSFORM, CRS_32633, n_zones=2
    )

    strong_half = result.labels[:, 21:]
    # Every stray pixel got absorbed: the strong half is one zone throughout.
    assert len(np.unique(strong_half[np.isfinite(strong_half)])) == 1
