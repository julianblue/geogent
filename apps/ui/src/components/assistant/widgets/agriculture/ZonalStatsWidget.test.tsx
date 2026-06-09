import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { zonalStatsWidget } from "./ZonalStatsWidget";
import type { ZonalStatsResult } from "./shared";

// Mirrors the backend ZonalStatsResponse the agent's zonal_stats_for_field tool
// returns verbatim (schemas/raster.py).
const result: ZonalStatsResult = {
  field_id: 7,
  index: "ndvi",
  scene: { id: "S2B_31UDQ_20260501_0_L2A", datetime: "2026-05-01T10:30:00Z", cloud_cover: 4.2 },
  stats: { mean: 0.63, min: 0.11, max: 0.92, std: 0.17, valid_pixels: 12034, nodata_pixels: 321 },
  histogram: { bin_edges: [0, 0.5, 1], counts: [20, 80] },
  cached: true,
};

describe("zonalStatsWidget", () => {
  it("registers under 'zonal-stats' with a field-scoped title", () => {
    expect(zonalStatsWidget.type).toBe("zonal-stats");
    expect(zonalStatsWidget.title?.(result)).toBe("NDVI stats — field 7");
  });

  it("renders mean/min/max + provenance inline", () => {
    const { Inline } = zonalStatsWidget;
    render(<Inline id="t1" data={result} />);
    expect(screen.getByText("Mean")).toBeInTheDocument();
    expect(screen.getByText("0.630")).toBeInTheDocument();
    expect(screen.getByText(/S2B_31UDQ_20260501_0_L2A/)).toBeInTheDocument();
    expect(screen.getByText(/4.2% cloud/)).toBeInTheDocument();
  });

  it("renders the expanded view with std, pixel counts and a distribution", () => {
    const Expanded = zonalStatsWidget.Expanded!;
    render(<Expanded id="t1" data={result} />);
    expect(screen.getByText(/NDVI zonal statistics — field 7/)).toBeInTheDocument();
    expect(screen.getByText("Std dev")).toBeInTheDocument();
    expect(screen.getByText("12,034")).toBeInTheDocument();
    expect(screen.getByText("Distribution")).toBeInTheDocument();
  });
});
