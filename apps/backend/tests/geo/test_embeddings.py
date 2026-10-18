"""Offline tests for the pure embedding maths (planted clusters, no store)."""

import numpy as np
import pytest

from geogent_backend.geo import embeddings as emb
from geogent_backend.services.embedding_service import _utm_geometry
from tests.tessera_fakes import (
    CRS_UTM,
    DIM,
    FIELD_SLICE,
    SIZE,
    TRANSFORM,
    field_geometry_4326,
    planted_window,
    unit,
)


def _mask() -> np.ndarray:
    geom = _utm_geometry(field_geometry_4326(), CRS_UTM)
    mask, _ = emb.field_mask(geom, (SIZE, SIZE), TRANSFORM)
    return mask


def test_field_mask_shrinks_inward_by_one_pixel() -> None:
    geom = _utm_geometry(field_geometry_4326(), CRS_UTM)
    mask, buffered = emb.field_mask(geom, (SIZE, SIZE), TRANSFORM)
    assert buffered
    # 20x20 px square, 10 m inward buffer -> the 18x18 interior
    assert mask.sum() == 18 * 18
    unbuffered, flag = emb.field_mask(geom, (SIZE, SIZE), TRANSFORM, buffer_m=0)
    assert not flag and unbuffered.sum() == 20 * 20


def test_field_mask_falls_back_when_buffer_empties_the_polygon() -> None:
    tiny = _utm_geometry(field_geometry_4326(inset_px=9), CRS_UTM)  # 2x2 px = 20 m wide
    mask, buffered = emb.field_mask(tiny, (SIZE, SIZE), TRANSFORM, buffer_m=15)
    assert not buffered and mask.sum() == 4


def test_year_stats_recovers_planted_cluster() -> None:
    w = planted_window([2024], {2024: unit(1) * 3}, {2024: np.zeros(DIM, np.float32)})
    s = emb.year_stats(w.emb[0], _mask())
    assert s.pixel_count == 18 * 18 and s.usable and s.masked_fraction == 0.0
    assert np.allclose(s.mean, unit(1) * 3, atol=0.01)
    assert s.heterogeneity < 0.001  # a uniform planted field


def test_year_stats_drops_nan_pixels_before_the_threshold() -> None:
    w = planted_window([2024], {2024: unit(1) * 3}, {2024: np.zeros(DIM, np.float32)})
    a = w.emb[0].copy()
    a[:, 25, 25] = np.nan  # a fully non-embedded pixel
    a[3, 26, 26] = np.nan  # a single NaN band is enough to drop the pixel
    s = emb.year_stats(a, _mask())
    assert s.pixel_count == 18 * 18 - 2
    assert s.masked_fraction == pytest.approx(2 / (18 * 18))
    assert np.isfinite(s.mean).all() and np.isfinite(s.std).all()

    # only 4 embedded pixels left -> counted as such, flagged unusable
    sparse = np.full_like(a, np.nan)
    sparse[:, 22:24, 22:24] = 1.0
    s = emb.year_stats(sparse, _mask())
    assert s.pixel_count == 4 and not s.usable

    none = emb.year_stats(np.full_like(a, np.nan), _mask())
    assert none.pixel_count == 0 and np.isnan(none.mean).all() and none.masked_fraction == 1.0


def test_window_mean_ignores_nan_pixels() -> None:
    a = np.ones((DIM, 4, 4), dtype=np.float32)
    a[:, 0, 0] = np.nan
    a[:, 1, 1] = 100.0
    a[2, 3, 3] = np.nan
    mean, n = emb.window_mean(a)
    assert n == 16 - 2
    assert np.isfinite(mean).all()
    assert mean[0] == pytest.approx((13 + 100) / 14)
    nan_mean, zero = emb.window_mean(np.full((DIM, 2, 2), np.nan, dtype=np.float32))
    assert zero == 0 and np.isnan(nan_mean).all()


def test_centring_removes_a_global_year_offset() -> None:
    rng = np.random.default_rng(1)
    crop = unit(2) * 2
    off_a, off_b = rng.normal(0, 5, DIM), rng.normal(0, 5, DIM)
    # the same crop in both years, but each year carries a large global offset
    centred, raw = emb.yoy_distance(off_a + crop, off_b + crop, off_a, off_b)
    assert centred == pytest.approx(0.0, abs=1e-9)
    assert raw > 0.1


def test_yoy_distance_detects_a_crop_change() -> None:
    off = np.zeros(DIM)
    same, _ = emb.yoy_distance(unit(1) * 2, unit(1) * 2, off, off)
    changed, _ = emb.yoy_distance(unit(1) * 2, unit(3) * 2, off, off)
    assert same == pytest.approx(0.0, abs=1e-9)
    assert changed == pytest.approx(1.0)  # orthogonal crops


def test_cosine_distance_is_nan_for_nan_input() -> None:
    assert np.isnan(emb.cosine_distance(np.full(DIM, np.nan), unit(0)))


def test_pca_rgb_separates_planted_clusters_and_stretches_to_1_255() -> None:
    w = planted_window(
        [2024], {2024: unit(1) * 4}, {2024: np.zeros(DIM, np.float32)}, noise=0.05, seed=3
    )
    rgb, valid, ratio = emb.pca_rgb(w.emb[0])
    assert rgb.dtype == np.uint8 and rgb.shape == (3, SIZE, SIZE) and valid.all()
    assert rgb.min() >= 1  # 0 is reserved for nodata
    # PC1 carries the field-vs-background contrast
    inside = rgb[0][FIELD_SLICE, FIELD_SLICE].mean()
    outside = rgb[0][:15, :15].mean()
    assert abs(float(inside) - float(outside)) > 150
    assert ratio[0] > 0.5 and ratio[0] >= ratio[1] >= ratio[2] >= 0
    assert ratio.sum() <= 1.0 + 1e-6


def test_pca_rgb_is_deterministic() -> None:
    w = planted_window([2024], {2024: unit(1) * 4}, {2024: np.zeros(DIM, np.float32)}, seed=3)
    a, _, _ = emb.pca_rgb(w.emb[0])
    b, _, _ = emb.pca_rgb(w.emb[0].copy())
    assert np.array_equal(a, b)


def test_pca_rgb_fits_on_finite_pixels_and_zeroes_the_rest() -> None:
    w = planted_window([2024], {2024: unit(1) * 4}, {2024: np.zeros(DIM, np.float32)}, seed=3)
    a = w.emb[0].copy()
    a[:, :5, :] = np.nan  # a band of non-embedded rows
    a[2, 30, 30] = np.nan  # one NaN band drops the whole pixel
    rgb, valid, ratio = emb.pca_rgb(a)
    assert not valid[:5].any() and not valid[30, 30]
    assert valid.sum() == SIZE * SIZE - 5 * SIZE - 1
    assert (rgb[:, ~valid] == 0).all() and (rgb[:, valid] >= 1).all()
    assert np.isfinite(ratio).all() and ratio[0] > 0.5


def test_pca_rgb_handles_degenerate_inputs() -> None:
    constant = np.ones((DIM, 6, 6), dtype=np.float32)
    rgb, valid, ratio = emb.pca_rgb(constant)
    assert valid.all() and (rgb >= 1).all() and ratio.sum() == 0  # no contrast, no crash

    empty_rgb, empty_valid, _ = emb.pca_rgb(np.full((DIM, 3, 3), np.nan, dtype=np.float32))
    assert not empty_valid.any() and (empty_rgb == 0).all()

    two_band = np.random.default_rng(0).normal(size=(2, 10, 10)).astype(np.float32)
    rgb2, valid2, ratio2 = emb.pca_rgb(two_band)
    assert valid2.all() and ratio2[2] == 0 and (rgb2[2] == 128).all()
