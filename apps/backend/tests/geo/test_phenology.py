"""Offline tests for the season-shape math (no network, no GDAL).

The series are synthetic but shaped like real crop seasons: a low bare-soil
baseline, a green-up ramp, a plateau/peak, and senescence. Metrics are asserted
with tolerances that reflect the daily-grid + smoothing pipeline rather than
pinning exact floats.
"""

from datetime import date, timedelta

import numpy as np

from geogent_backend.geo import phenology
from geogent_backend.geo.phenology import SeriesPoint

ORIGIN = date(2025, 3, 1)


def _season(
    peak_offset: int = 120,
    peak_value: float = 0.85,
    floor: float = 0.15,
    length: int = 240,
    step: int = 5,
    scale: float = 1.0,
    year: int = ORIGIN.year,
) -> list[SeriesPoint]:
    """A triangular season sampled every ``step`` days from ``ORIGIN``.

    ``year`` moves the whole season into another calendar year, which is how a
    baseline season is built: same window, different year.
    """
    origin = ORIGIN.replace(year=year)
    points = []
    for d in range(0, length + 1, step):
        if d <= peak_offset:
            frac = d / peak_offset
        else:
            frac = max(0.0, 1.0 - (d - peak_offset) / (length - peak_offset))
        value = floor + (peak_value - floor) * frac * scale
        points.append(SeriesPoint(day=origin + timedelta(days=d), value=value))
    return points


def test_season_metrics_find_peak_and_bounds() -> None:
    metrics = phenology.season_metrics(_season(), ORIGIN)

    assert metrics["status"] == "ok"
    assert abs(metrics["peak_value"] - 0.85) < 0.05
    # Peak at +120 days from 1 March.
    assert abs((date.fromisoformat(metrics["peak_date"]) - ORIGIN).days - 120) <= 10
    assert metrics["start_of_season"] is not None
    assert metrics["end_of_season"] is not None
    assert metrics["season_length_days"] > 100
    assert metrics["seasonal_integral"] > 0
    assert metrics["greenup_rate_per_day"] > 0
    assert metrics["senescence_rate_per_day"] > 0


def test_season_metrics_reject_a_series_too_sparse_to_read() -> None:
    sparse = [SeriesPoint(day=ORIGIN + timedelta(days=30 * i), value=0.4) for i in range(3)]
    metrics = phenology.season_metrics(sparse, ORIGIN)

    assert metrics["status"] == "insufficient_data"
    assert metrics["n_observations"] == 3
    assert "peak_value" not in metrics


def test_season_metrics_report_the_largest_observation_gap() -> None:
    """A curve interpolated across a month-long hole must say so."""
    points = [SeriesPoint(day=ORIGIN + timedelta(days=d), value=0.3 + d / 400) for d in (0, 5, 10)]
    points += [SeriesPoint(day=ORIGIN + timedelta(days=d), value=0.7) for d in (55, 60, 65)]
    metrics = phenology.season_metrics(points, ORIGIN)

    assert metrics["status"] == "ok"
    assert metrics["max_gap_days"] == 45


def test_earlier_peak_shows_up_as_an_earlier_peak_date() -> None:
    early = phenology.season_metrics(_season(peak_offset=80), ORIGIN)
    late = phenology.season_metrics(_season(peak_offset=160), ORIGIN)

    assert date.fromisoformat(early["peak_date"]) < date.fromisoformat(late["peak_date"])


def test_a_weaker_season_carries_a_smaller_integral() -> None:
    strong = phenology.season_metrics(_season(), ORIGIN)
    weak = phenology.season_metrics(_season(scale=0.5), ORIGIN)

    assert weak["seasonal_integral"] < strong["seasonal_integral"]
    assert weak["amplitude"] < strong["amplitude"]


def test_anomaly_detects_a_season_running_below_its_own_history() -> None:
    current = _season(scale=0.6)
    baselines = {
        2024: _season(year=2024),
        2023: _season(year=2023),
    }
    origins = {2024: ORIGIN.replace(year=2024), 2023: ORIGIN.replace(year=2023)}

    result = phenology.baseline_anomaly(current, ORIGIN, baselines, origins)

    assert result["status"] == "ok"
    assert result["baseline_years"] == [2023, 2024]
    assert result["mean_difference"] < 0
    assert result["fraction_of_season_below_baseline"] > 0.8
    assert result["largest_shortfall"]["difference"] < 0


def test_anomaly_reports_no_baseline_rather_than_inventing_one() -> None:
    thin = {2024: [SeriesPoint(day=ORIGIN.replace(year=2024), value=0.4)]}
    result = phenology.baseline_anomaly(_season(), ORIGIN, thin, {2024: ORIGIN.replace(year=2024)})

    assert result["status"] == "no_baseline"


def test_anomaly_aligns_on_season_offset_so_winter_crops_work() -> None:
    """A season crossing the new year must compare cleanly with the previous
    one; day-of-year alignment would split it around 31 December."""
    winter_origin = date(2024, 10, 1)
    current = [
        SeriesPoint(day=winter_origin + timedelta(days=d), value=0.2 + d / 500)
        for d in range(0, 240, 10)
    ]
    prev_origin = date(2023, 10, 1)
    previous = [
        SeriesPoint(day=prev_origin + timedelta(days=d), value=0.4 + d / 500)
        for d in range(0, 240, 10)
    ]

    result = phenology.baseline_anomaly(
        current, winter_origin, {2023: previous}, {2023: prev_origin}
    )

    assert result["status"] == "ok"
    assert result["n_days_compared"] > 200  # the whole overlapping season, not a fragment
    assert result["mean_difference"] < 0  # this winter is behind last winter


def test_sample_curve_downsamples_and_stays_json_safe() -> None:
    grid, curve = phenology.daily_curve(_season(), ORIGIN)
    sampled = phenology.sample_curve(grid, curve, ORIGIN, max_points=20)

    assert 0 < len(sampled) <= 20
    assert all(isinstance(p["value"], float) and np.isfinite(p["value"]) for p in sampled)
    assert date.fromisoformat(sampled[0]["date"]) >= ORIGIN
