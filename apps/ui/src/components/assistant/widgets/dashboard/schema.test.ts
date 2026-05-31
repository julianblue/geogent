import { describe, expect, it } from "vitest";

import { dashboardSpecSchema, panelSchema } from "./schema";

describe("dashboardSpecSchema", () => {
  it("parses a full multi-panel dashboard", () => {
    const result = dashboardSpecSchema.safeParse({
      title: "Field 7 — NDVI health",
      layout: "grid",
      panels: [
        { type: "stat", stats: [{ label: "Mean NDVI", value: 0.62 }] },
        {
          type: "timeseries",
          series: [{ key: "ndvi", points: [{ x: "2026-03-01", y: 0.4 }] }],
        },
        { type: "histogram", bins: [{ label: "0.2-0.4", count: 88 }] },
        { type: "table", columns: [{ key: "scene", header: "Scene" }], rows: [{ scene: "S2B" }] },
      ],
    });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.layout).toBe("grid");
      expect(result.data.panels).toHaveLength(4);
    }
  });

  it("leaves layout undefined when omitted (default applied at render)", () => {
    const result = dashboardSpecSchema.safeParse({
      panels: [{ type: "stat", stats: [{ label: "x", value: 1 }] }],
    });
    expect(result.success).toBe(true);
    if (result.success) expect(result.data.layout).toBeUndefined();
  });

  it("rejects an empty panel list", () => {
    expect(dashboardSpecSchema.safeParse({ panels: [] }).success).toBe(false);
  });

  it("rejects an invalid layout", () => {
    const result = dashboardSpecSchema.safeParse({
      layout: "masonry",
      panels: [{ type: "stat", stats: [{ label: "x", value: 1 }] }],
    });
    expect(result.success).toBe(false);
  });
});

describe("panelSchema discriminated union", () => {
  it("rejects an unknown panel type", () => {
    expect(panelSchema.safeParse({ type: "scatterplot", data: [] }).success).toBe(false);
  });

  it("accepts a stat value as either number or string", () => {
    const result = panelSchema.safeParse({
      type: "stat",
      stats: [
        { label: "mean", value: 0.62 },
        { label: "trend", value: "rising" },
      ],
    });
    expect(result.success).toBe(true);
  });

  it("requires histogram bins to have label and count", () => {
    expect(panelSchema.safeParse({ type: "histogram", bins: [{ label: "a" }] }).success).toBe(
      false,
    );
  });
});
