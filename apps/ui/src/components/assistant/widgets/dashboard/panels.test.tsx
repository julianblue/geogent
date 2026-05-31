import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { PanelView, mergeSeriesRows } from "./panels";
import { panelSchema } from "./schema";

describe("mergeSeriesRows", () => {
  it("merges two series sharing x values into one row per x", () => {
    const rows = mergeSeriesRows([
      {
        key: "ndvi",
        points: [
          { x: "2026-01", y: 0.3 },
          { x: "2026-02", y: 0.5 },
        ],
      },
      {
        key: "ndwi",
        points: [
          { x: "2026-01", y: 0.1 },
          { x: "2026-02", y: 0.2 },
        ],
      },
    ]);
    expect(rows).toEqual([
      { x: "2026-01", ndvi: 0.3, ndwi: 0.1 },
      { x: "2026-02", ndvi: 0.5, ndwi: 0.2 },
    ]);
  });

  it("sorts rows by x and tolerates disjoint x across series", () => {
    const rows = mergeSeriesRows([
      { key: "a", points: [{ x: "2026-03", y: 1 }] },
      { key: "b", points: [{ x: "2026-01", y: 2 }] },
    ]);
    expect(rows.map((r) => r.x)).toEqual(["2026-01", "2026-03"]);
  });
});

describe("PanelView", () => {
  it("renders a stat panel's labels and values", () => {
    const panel = panelSchema.parse({
      type: "stat",
      stats: [{ label: "Mean NDVI", value: 0.62, unit: "idx" }],
    });
    render(<PanelView panel={panel} />);
    expect(screen.getByText("Mean NDVI")).toBeInTheDocument();
    expect(screen.getByText("0.62")).toBeInTheDocument();
    expect(screen.getByText("idx")).toBeInTheDocument();
  });

  it("renders a table panel's headers and cells", () => {
    const panel = panelSchema.parse({
      type: "table",
      columns: [
        { key: "scene", header: "Scene" },
        { key: "mean", header: "Mean", align: "right" },
      ],
      rows: [{ scene: "S2B_31UGS", mean: 0.62 }],
    });
    render(<PanelView panel={panel} />);
    expect(screen.getByText("Scene")).toBeInTheDocument();
    expect(screen.getByText("Mean")).toBeInTheDocument();
    expect(screen.getByText("S2B_31UGS")).toBeInTheDocument();
    expect(screen.getByText("0.62")).toBeInTheDocument();
  });

  it("renders chart panels without throwing", () => {
    const ts = panelSchema.parse({
      type: "timeseries",
      series: [{ key: "ndvi", points: [{ x: "2026-01", y: 0.4 }] }],
    });
    const hist = panelSchema.parse({ type: "histogram", bins: [{ label: "0-0.2", count: 3 }] });
    expect(() => render(<PanelView panel={ts} />)).not.toThrow();
    expect(() => render(<PanelView panel={hist} />)).not.toThrow();
  });
});
