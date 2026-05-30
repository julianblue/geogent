import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { dashboardWidget } from "./DashboardWidget";
import { dashboardSpecSchema } from "./schema";

// The exact spec shape the agent emits via `render_dashboard`. Rendering the
// registered widget proves the composition path end-to-end: spec → layout
// template → multiple panel types in one view (the UI half of the round-trip).
const fieldHealthSpec = dashboardSpecSchema.parse({
  title: "Field 7 — NDVI health",
  layout: "grid",
  panels: [
    { type: "stat", stats: [{ label: "Mean NDVI", value: 0.62 }] },
    {
      type: "timeseries",
      title: "Seasonal NDVI",
      series: [{ key: "ndvi", points: [{ x: "2026-03-01", y: 0.4 }] }],
    },
    { type: "table", columns: [{ key: "scene", header: "Scene" }], rows: [{ scene: "S2B_31UGS" }] },
  ],
});

describe("dashboardWidget", () => {
  it("is registered under the 'dashboard' type with a title", () => {
    expect(dashboardWidget.type).toBe("dashboard");
    expect(dashboardWidget.title?.(fieldHealthSpec)).toBe("Field 7 — NDVI health");
  });

  it("composes multiple panel types into one inline view", () => {
    const { Inline } = dashboardWidget;
    render(<Inline id="t1" data={fieldHealthSpec} />);
    // Dashboard title + a panel title + a stat + a table cell all coexist.
    expect(screen.getByText("Field 7 — NDVI health")).toBeInTheDocument();
    expect(screen.getByText("Seasonal NDVI")).toBeInTheDocument();
    expect(screen.getByText("Mean NDVI")).toBeInTheDocument();
    expect(screen.getByText("0.62")).toBeInTheDocument();
    expect(screen.getByText("S2B_31UGS")).toBeInTheDocument();
  });

  it("renders the expanded workspace view", () => {
    const Expanded = dashboardWidget.Expanded!;
    render(<Expanded id="t1" data={fieldHealthSpec} />);
    expect(screen.getByText("Field 7 — NDVI health")).toBeInTheDocument();
    expect(screen.getByText("S2B_31UGS")).toBeInTheDocument();
  });
});
