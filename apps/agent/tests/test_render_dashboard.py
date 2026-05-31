"""Unit tests for the `render_dashboard` frontend tool and its `DashboardSpec`.

`render_dashboard` is a pure client-rendered tool (no backend call), so these
tests exercise the Pydantic spec — the discriminated panel union, defaults, and
validation — plus the tool's acknowledgement payload.
"""

import pytest
from pydantic import ValidationError

from geogent_agent.tools import render_dashboard
from geogent_agent.tools.frontend_actions import (
    DashboardSpec,
    HistogramPanel,
    StatPanel,
    TablePanel,
    TimeSeriesPanel,
)

_FIELD_HEALTH_SPEC = {
    "title": "Field 7 — NDVI health",
    "layout": "grid",
    "panels": [
        {
            "type": "stat",
            "stats": [
                {"label": "Mean NDVI", "value": 0.62},
                {"label": "Valid pixels", "value": 10432},
            ],
        },
        {
            "type": "timeseries",
            "title": "Seasonal NDVI",
            "series": [
                {
                    "key": "ndvi",
                    "label": "NDVI",
                    "points": [
                        {"x": "2026-03-01", "y": 0.4},
                        {"x": "2026-04-01", "y": 0.6},
                    ],
                }
            ],
        },
        {
            "type": "histogram",
            "title": "Distribution",
            "bins": [{"label": "0.2-0.4", "count": 88}],
        },
        {
            "type": "table",
            "columns": [{"key": "scene", "header": "Scene"}],
            "rows": [{"scene": "S2B_31UGS_20260501"}],
        },
    ],
}


def test_dashboard_spec_resolves_each_panel_type() -> None:
    spec = DashboardSpec.model_validate(_FIELD_HEALTH_SPEC)
    assert [type(p) for p in spec.panels] == [
        StatPanel,
        TimeSeriesPanel,
        HistogramPanel,
        TablePanel,
    ]
    assert spec.layout == "grid"


def test_layout_defaults_to_stack() -> None:
    spec = DashboardSpec.model_validate(
        {"panels": [{"type": "stat", "stats": [{"label": "x", "value": 1}]}]}
    )
    assert spec.layout == "stack"


def test_stat_value_accepts_number_or_string() -> None:
    spec = DashboardSpec.model_validate(
        {
            "panels": [
                {
                    "type": "stat",
                    "stats": [
                        {"label": "n", "value": 0.62},
                        {"label": "label", "value": "high"},
                    ],
                }
            ]
        }
    )
    assert isinstance(spec.panels[0], StatPanel)
    assert spec.panels[0].stats[1].value == "high"


def test_unknown_panel_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        DashboardSpec.model_validate({"panels": [{"type": "scatterplot", "data": []}]})


def test_empty_panel_list_is_rejected() -> None:
    # min_length mirrors the browser Zod `.min(1)`, so the agent fails fast with
    # a recoverable error instead of after the round trip.
    with pytest.raises(ValidationError):
        DashboardSpec.model_validate({"panels": []})


def test_empty_panel_data_is_rejected() -> None:
    with pytest.raises(ValidationError):
        DashboardSpec.model_validate({"panels": [{"type": "histogram", "bins": []}]})


def test_render_dashboard_acks_with_panel_count() -> None:
    result = render_dashboard.invoke({"spec": _FIELD_HEALTH_SPEC})
    assert result == {"queued_dashboard": True, "panel_count": 4}
