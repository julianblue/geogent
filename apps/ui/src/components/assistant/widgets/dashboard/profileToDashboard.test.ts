import { describe, expect, it } from "vitest";

import { dashboardSpecSchema } from "./schema";
import { profileToDashboard, type FieldEmbeddingProfileSummary } from "./profileToDashboard";

const summary: FieldEmbeddingProfileSummary = {
  field_id: 7,
  area_ha: 12.34,
  years: [2020, 2021, 2022],
  grid: { resolution_m: 10 },
  per_year: [
    { year: 2020, pixel_count: 1234, heterogeneity: 0.1234, usable: true },
    { year: 2021, pixel_count: 1230, heterogeneity: 0.2, usable: true },
    { year: 2022, pixel_count: 1228, heterogeneity: null, usable: true },
  ],
  yoy: [
    { from_year: 2020, to_year: 2021, cosine_distance_centred: 0.2, cosine_distance_raw: 0.05 },
    { from_year: 2021, to_year: 2022, cosine_distance_centred: 0.4, cosine_distance_raw: 0.07 },
  ],
  rotation_screen: { valid: true, min_area_ha: 1 },
};

describe("profileToDashboard", () => {
  it("maps a full summary to stats, a YoY chart and a per-year table", () => {
    const spec = profileToDashboard(summary);
    expect(spec).not.toBeNull();
    expect(dashboardSpecSchema.safeParse(spec).success).toBe(true);
    expect(spec!.title).toBe("Field 7 — embedding profile 2020–2022");
    expect(spec!.panels.map((p) => p.type)).toEqual(["stat", "timeseries", "table"]);

    const [stat, ts, table] = spec!.panels;
    if (stat.type !== "stat" || ts.type !== "timeseries" || table.type !== "table") {
      throw new Error("unexpected panel types");
    }
    expect(stat.stats.map((s) => s.value)).toEqual([0.3, "Valid", 1234]);
    expect(ts.series).toEqual([
      {
        key: "centred",
        label: "Centred",
        points: [
          { x: "2020→2021", y: 0.2 },
          { x: "2021→2022", y: 0.4 },
        ],
      },
      {
        key: "raw",
        label: "Raw",
        points: [
          { x: "2020→2021", y: 0.05 },
          { x: "2021→2022", y: 0.07 },
        ],
      },
    ]);
    expect(table.rows[0]).toEqual({
      year: "2020",
      pixels: 1234,
      heterogeneity: 0.123,
      usable: "Yes",
    });
    expect(table.rows[2].heterogeneity).toBe("—");
  });

  it("flags a field below the rotation-screen minimum area", () => {
    const spec = profileToDashboard({
      ...summary,
      area_ha: 0.4,
      rotation_screen: { valid: false, min_area_ha: 1 },
    });
    const stat = spec!.panels[0];
    if (stat.type !== "stat") throw new Error("expected stat panel");
    expect(stat.stats[1]).toMatchObject({
      value: "Not valid",
      hint: "Field is 0.4 ha; needs ≥ 1 ha",
    });
  });

  it("drops year pairs touching an unusable year but keeps them in the table", () => {
    const spec = profileToDashboard({
      ...summary,
      per_year: [
        { year: 2020, pixel_count: 1234, heterogeneity: 0.1, usable: true },
        { year: 2021, pixel_count: 3, heterogeneity: null, usable: false },
        { year: 2022, pixel_count: 1228, heterogeneity: 0.1, usable: true },
      ],
      yoy: [
        { from_year: 2020, to_year: 2021, cosine_distance_centred: 0.9, cosine_distance_raw: 0.9 },
        { from_year: 2021, to_year: 2022, cosine_distance_centred: 0.9, cosine_distance_raw: 0.9 },
      ],
    });
    // No plottable pair remains → no chart, and "—" instead of a fake mean.
    expect(spec!.panels.map((p) => p.type)).toEqual(["stat", "table"]);
    const [stat, table] = spec!.panels;
    if (stat.type !== "stat" || table.type !== "table") throw new Error("unexpected panels");
    expect(stat.stats[0]).toMatchObject({ value: "—", hint: "No usable year pairs" });
    expect(table.rows[1]).toMatchObject({ year: "2021", pixels: 3, usable: "No" });
  });

  it("skips non-finite distances and omits an all-missing series", () => {
    const spec = profileToDashboard({
      ...summary,
      yoy: [
        { from_year: 2020, to_year: 2021, cosine_distance_centred: 0.2, cosine_distance_raw: null },
        {
          from_year: 2021,
          to_year: 2022,
          cosine_distance_centred: null,
          cosine_distance_raw: null,
        },
      ],
    });
    const ts = spec!.panels[1];
    if (ts.type !== "timeseries") throw new Error("expected timeseries panel");
    expect(ts.series.map((s) => s.key)).toEqual(["centred"]);
    expect(ts.series[0].points).toEqual([{ x: "2020→2021", y: 0.2 }]);
  });

  it("omits the chart for an empty yoy list (single-year profile)", () => {
    const spec = profileToDashboard({
      ...summary,
      years: [2020],
      per_year: [summary.per_year![0]],
      yoy: [],
    });
    expect(spec!.panels.map((p) => p.type)).toEqual(["stat", "table"]);
    expect(dashboardSpecSchema.safeParse(spec).success).toBe(true);
  });

  it("returns null for missing or empty summaries", () => {
    expect(profileToDashboard(null)).toBeNull();
    expect(profileToDashboard(undefined)).toBeNull();
    expect(profileToDashboard({})).toBeNull();
    expect(profileToDashboard({ per_year: [], yoy: [] })).toBeNull();
  });

  it("tolerates a sparse summary with no rotation screen or area", () => {
    const spec = profileToDashboard({ per_year: [{ year: 2020 }] });
    const stat = spec!.panels[0];
    if (stat.type !== "stat") throw new Error("expected stat panel");
    expect(stat.stats.map((s) => s.value)).toEqual(["—", "—", "—"]);
    expect(spec!.title).toBe("Field — embedding profile 2020–2020");
  });
});
