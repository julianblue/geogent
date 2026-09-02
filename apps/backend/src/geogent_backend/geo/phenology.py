"""Season-shape analysis over an index time series.

A per-scene series of field means is data, not an answer. What an agronomist
actually reads off it is the *shape*: when the crop greened up, how high and
how fast it peaked, when it senesced, how much cumulative canopy the season
carried, and whether that differs from what this field usually does. This
module turns the raw points into those numbers so the agent reasons about
metrics instead of eyeballing a list.

Two design choices worth knowing:

**Irregular sampling.** Optical scenes arrive on an uneven cadence (revisit,
plus whatever the cloud mask removed), so every metric is computed on a daily
grid obtained by linear interpolation between observations, then smoothed with
a centred moving average. Interpolation never invents data outside the
observed span, and long gaps are reported (``max_gap_days``) so a curve built
across a three-week hole can be discounted.

**Baseline alignment by season offset, not day-of-year.** A baseline year is
compared on *days since the start of the season window*, not calendar DOY. That
is what makes the comparison correct for winter crops, whose season crosses the
new year — DOY alignment would tear those seasons in half.

Pure numpy, no I/O: the raster service feeds it points and stores what comes
back.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from datetime import date

import numpy as np

# Below this many usable observations the shape is not identifiable and every
# metric would be an artifact of interpolation.
MIN_POINTS_FOR_SHAPE = 5

# Fraction of the season's amplitude at which the crop is considered "up"
# (start of season) and "down" again (end of season). 20% is the common
# convention in phenology literature and is robust to a noisy baseline.
SEASON_THRESHOLD_FRACTION = 0.2

# Centred moving-average window over the daily grid. Roughly one Sentinel-2
# revisit cycle on each side: long enough to damp per-scene noise, short enough
# to keep a real green-up edge.
DEFAULT_SMOOTHING_DAYS = 15


@dataclass(frozen=True)
class SeriesPoint:
    """One usable observation: a date and the field-mean index on that date."""

    day: date
    value: float


def _axis(points: list[SeriesPoint], origin: date) -> np.ndarray:
    """Observation dates as days since ``origin`` (float, for interpolation)."""
    return np.array([(p.day - origin).days for p in points], dtype="float64")


def _values(points: list[SeriesPoint]) -> np.ndarray:
    return np.array([p.value for p in points], dtype="float64")


def _moving_average(values: np.ndarray, window: int) -> np.ndarray:
    """Centred moving average with edge padding (keeps length and endpoints)."""
    if window <= 1 or values.size == 0:
        return values
    window = min(window, values.size if values.size % 2 else values.size - 1)
    if window < 3:
        return values
    if window % 2 == 0:
        window -= 1
    pad = window // 2
    padded = np.pad(values, pad, mode="edge")
    kernel = np.ones(window) / window
    return np.convolve(padded, kernel, mode="valid")


def daily_curve(
    points: list[SeriesPoint],
    origin: date,
    smoothing_days: int = DEFAULT_SMOOTHING_DAYS,
) -> tuple[np.ndarray, np.ndarray]:
    """Interpolate the observations onto a daily grid and smooth them.

    Returns ``(days_since_origin, smoothed_values)``. The grid spans only the
    observed range — nothing is extrapolated.
    """
    days = _axis(points, origin)
    vals = _values(points)
    order = np.argsort(days)
    days, vals = days[order], vals[order]
    grid = np.arange(days[0], days[-1] + 1, dtype="float64")
    interpolated = np.interp(grid, days, vals)
    return grid, _moving_average(interpolated, smoothing_days)


def _crossings(grid: np.ndarray, curve: np.ndarray, level: float, peak_idx: int) -> tuple:
    """First up-crossing before the peak and last down-crossing after it."""
    before = np.nonzero(curve[: peak_idx + 1] >= level)[0]
    after = np.nonzero(curve[peak_idx:] >= level)[0]
    sos = float(grid[before[0]]) if before.size else None
    eos = float(grid[peak_idx + after[-1]]) if after.size else None
    return sos, eos


def season_metrics(
    points: list[SeriesPoint],
    origin: date,
    smoothing_days: int = DEFAULT_SMOOTHING_DAYS,
) -> dict:
    """Phenology metrics for one season's worth of observations.

    Always returns a dict. When the series is too thin to have an identifiable
    shape, ``status`` is ``"insufficient_data"`` and the metrics are absent —
    callers report that rather than presenting interpolation noise as phenology.
    """
    usable = sorted(
        (p for p in points if np.isfinite(p.value)),
        key=lambda p: p.day,
    )
    if len(usable) < MIN_POINTS_FOR_SHAPE:
        return {
            "status": "insufficient_data",
            "n_observations": len(usable),
            "reason": (
                f"only {len(usable)} usable observations "
                f"(need {MIN_POINTS_FOR_SHAPE}) — too sparse to read a season shape"
            ),
        }

    grid, curve = daily_curve(usable, origin, smoothing_days)
    peak_idx = int(np.argmax(curve))
    peak_value = float(curve[peak_idx])
    trough = float(np.min(curve))
    amplitude = peak_value - trough
    level = trough + SEASON_THRESHOLD_FRACTION * amplitude
    sos, eos = _crossings(grid, curve, level, peak_idx)

    # Cumulative canopy over the season: area between the curve and its own
    # trough. Proportional to intercepted radiation, so it tracks biomass far
    # better than a peak value alone.
    integral = float(np.trapezoid(np.clip(curve - trough, 0.0, None), grid))

    days = _axis(usable, origin)
    gaps = np.diff(np.sort(days))

    def _as_date(offset: float | None) -> str | None:
        if offset is None:
            return None
        return (origin + _timedelta_days(offset)).isoformat()

    greenup_days = (grid[peak_idx] - sos) if sos is not None else None
    senescence_days = (eos - grid[peak_idx]) if eos is not None else None

    return {
        "status": "ok",
        "n_observations": len(usable),
        "peak_value": round(peak_value, 4),
        "peak_date": _as_date(float(grid[peak_idx])),
        "trough_value": round(trough, 4),
        "amplitude": round(amplitude, 4),
        "start_of_season": _as_date(sos),
        "end_of_season": _as_date(eos),
        "season_length_days": (
            int(eos - sos) if sos is not None and eos is not None and eos >= sos else None
        ),
        "seasonal_integral": round(integral, 3),
        # Index units per day: how fast the canopy closed, and how fast it went.
        "greenup_rate_per_day": (
            round(amplitude / greenup_days, 5) if greenup_days and greenup_days > 0 else None
        ),
        "senescence_rate_per_day": (
            round(amplitude / senescence_days, 5)
            if senescence_days and senescence_days > 0
            else None
        ),
        "max_gap_days": int(gaps.max()) if gaps.size else 0,
        "observed_span_days": int(days[-1] - days[0]),
    }


def _timedelta_days(offset: float):
    from datetime import timedelta

    return timedelta(days=int(round(offset)))


def baseline_anomaly(
    season: list[SeriesPoint],
    season_origin: date,
    baselines: dict[int, list[SeriesPoint]],
    baseline_origins: dict[int, date],
    smoothing_days: int = DEFAULT_SMOOTHING_DAYS,
) -> dict:
    """Compare this season against previous seasons of the same field.

    Each baseline season is placed on the same "days since the start of the
    window" axis as the current one (see the module docstring on why this beats
    day-of-year), interpolated to a daily grid, and reduced to a per-day mean
    and spread across years. The current curve is then differenced against it.

    Returns a summary plus a coarse per-day comparison the caller can chart.
    """
    usable_years = {
        year: pts
        for year, pts in baselines.items()
        if len([p for p in pts if np.isfinite(p.value)]) >= MIN_POINTS_FOR_SHAPE
    }
    if not usable_years:
        return {
            "status": "no_baseline",
            "reason": "no previous season had enough usable observations to compare against",
        }
    if len([p for p in season if np.isfinite(p.value)]) < MIN_POINTS_FOR_SHAPE:
        return {
            "status": "insufficient_data",
            "reason": "the current season is too sparse to compare",
        }

    cur_grid, cur_curve = daily_curve(season, season_origin, smoothing_days)

    stacked: list[np.ndarray] = []
    for year, pts in sorted(usable_years.items()):
        grid, curve = daily_curve(pts, baseline_origins[year], smoothing_days)
        # Resample each baseline year onto the current season's day axis; days
        # outside that year's observed span become NaN rather than extrapolated.
        resampled = np.interp(cur_grid, grid, curve, left=np.nan, right=np.nan)
        stacked.append(resampled)

    matrix = np.vstack(stacked)
    with warnings.catch_warnings():
        # Days no baseline year covers are all-NaN columns; that is the expected
        # shape of a partial overlap, not a problem to warn about.
        warnings.simplefilter("ignore", category=RuntimeWarning)
        baseline_mean = np.nanmean(matrix, axis=0)
        baseline_std = np.nanstd(matrix, axis=0)
    comparable = np.isfinite(baseline_mean)
    if not comparable.any():
        return {
            "status": "no_overlap",
            "reason": "baseline years do not overlap the current season's dates",
        }

    diff = np.where(comparable, cur_curve - baseline_mean, np.nan)
    # Guard the z-score against a near-zero spread (identical baseline years).
    spread = np.where(baseline_std > 1e-6, baseline_std, np.nan)
    z = diff / spread

    finite_diff = diff[np.isfinite(diff)]
    worst_idx = int(np.nanargmin(diff)) if finite_diff.size else None
    best_idx = int(np.nanargmax(diff)) if finite_diff.size else None
    mean_diff = float(np.mean(finite_diff)) if finite_diff.size else 0.0
    finite_z = z[np.isfinite(z)]

    def _date_at(idx: int | None) -> str | None:
        if idx is None:
            return None
        return (season_origin + _timedelta_days(float(cur_grid[idx]))).isoformat()

    return {
        "status": "ok",
        "baseline_years": sorted(usable_years),
        "n_days_compared": int(comparable.sum()),
        "mean_difference": round(mean_diff, 4),
        "mean_z_score": (round(float(np.mean(finite_z)), 3) if finite_z.size else None),
        "fraction_of_season_below_baseline": round(float((finite_diff < 0).mean()), 3)
        if finite_diff.size
        else None,
        "largest_shortfall": {
            "date": _date_at(worst_idx),
            "difference": round(float(diff[worst_idx]), 4) if worst_idx is not None else None,
        },
        "largest_surplus": {
            "date": _date_at(best_idx),
            "difference": round(float(diff[best_idx]), 4) if best_idx is not None else None,
        },
    }


def sample_curve(
    grid: np.ndarray, curve: np.ndarray, origin: date, max_points: int = 40
) -> list[dict]:
    """Downsample a daily curve to a chart-sized, JSON-safe series."""
    if grid.size == 0:
        return []
    step = max(1, int(np.ceil(grid.size / max_points)))
    idx = np.arange(0, grid.size, step)
    return [
        {
            "date": (origin + _timedelta_days(float(grid[i]))).isoformat(),
            "value": round(float(curve[i]), 4),
        }
        for i in idx
        if np.isfinite(curve[i])
    ]
