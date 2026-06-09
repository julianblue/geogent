import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { indexTimeSeriesWidget } from "./IndexTimeSeriesWidget";
import type { TimeSeriesResult } from "./shared";

// Mirrors the backend TimeSeriesResultResponse the seasonal tool returns.
const result: TimeSeriesResult = {
  job_id: "11111111-1111-1111-1111-111111111111",
  status: "succeeded",
  field_id: 7,
  index: "ndvi",
  points: [
    {
      scene_id: "S2A_31UDQ_20250412_0_L2A",
      datetime: "2025-04-12T10:30:00Z",
      cloud_cover: 6.1,
      mean: 0.51,
      min: 0.15,
      max: 0.81,
      std: 0.12,
      valid_pixels: 11700,
    },
    {
      scene_id: "S2B_31UDQ_20250705_0_L2A",
      datetime: "2025-07-05T10:30:00Z",
      cloud_cover: 2.3,
      mean: 0.74,
      min: 0.3,
      max: 0.93,
      std: 0.1,
      valid_pixels: 11980,
    },
  ],
  error: null,
};

describe("indexTimeSeriesWidget", () => {
  it("registers under 'index-time-series' with a field-scoped title", () => {
    expect(indexTimeSeriesWidget.type).toBe("index-time-series");
    expect(indexTimeSeriesWidget.title?.(result)).toBe("Seasonal NDVI — field 7");
  });

  it("summarises scene count and latest value inline", () => {
    const { Inline } = indexTimeSeriesWidget;
    render(<Inline id="t1" data={result} />);
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("0.740")).toBeInTheDocument();
  });

  it("renders a per-scene table in the expanded view", () => {
    const Expanded = indexTimeSeriesWidget.Expanded!;
    render(<Expanded id="t1" data={result} />);
    expect(screen.getByText(/Seasonal NDVI — field 7/)).toBeInTheDocument();
    expect(screen.getByText("S2A_31UDQ_20250412_0_L2A")).toBeInTheDocument();
    expect(screen.getByText("S2B_31UDQ_20250705_0_L2A")).toBeInTheDocument();
  });

  it("handles an empty (no cloud-free scenes) result", () => {
    const empty: TimeSeriesResult = { ...result, points: [] };
    const { Inline } = indexTimeSeriesWidget;
    render(<Inline id="t1" data={empty} />);
    expect(screen.getByText(/No cloud-free scenes in range/)).toBeInTheDocument();
  });
});
