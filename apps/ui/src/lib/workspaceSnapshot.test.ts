import { describe, expect, it } from "vitest";

import {
  buildSnapshot,
  isEmptySnapshot,
  parseSnapshot,
  snapshotsEqual,
  type SnapshotInput,
} from "./workspaceSnapshot";

const baseInput: SnapshotInput = {
  viewport: { longitude: 10, latitude: 52, zoom: 8, bounds: null },
  layers: [],
  sentinel2Scene: null,
  selectedFieldId: null,
  openWidgetIds: [],
  pinnedWidgetIds: [],
  activeWidgetId: null,
};

describe("buildSnapshot", () => {
  it("captures only the camera fields of the viewport (drops bounds)", () => {
    const snap = buildSnapshot({
      ...baseInput,
      viewport: {
        longitude: 10,
        latitude: 52,
        zoom: 8,
        bounds: { west: 0, south: 0, east: 1, north: 1 },
      },
    });
    expect(snap.viewport).toEqual({ longitude: 10, latitude: 52, zoom: 8 });
  });

  it("groups workspace widget ids under `workspace`", () => {
    const snap = buildSnapshot({
      ...baseInput,
      openWidgetIds: ["a", "b"],
      pinnedWidgetIds: ["a"],
      activeWidgetId: "b",
    });
    expect(snap.workspace).toEqual({
      openWidgetIds: ["a", "b"],
      pinnedWidgetIds: ["a"],
      activeWidgetId: "b",
    });
  });
});

describe("parseSnapshot", () => {
  it("round-trips a built snapshot", () => {
    const snap = buildSnapshot({ ...baseInput, selectedFieldId: 7, openWidgetIds: ["w1"] });
    expect(parseSnapshot(snap)).toEqual(snap);
  });

  it("rejects unknown/missing versions as a clean reset", () => {
    expect(parseSnapshot(null)).toBeNull();
    expect(parseSnapshot("nope")).toBeNull();
    expect(parseSnapshot({ v: 2, layers: [] })).toBeNull();
    expect(parseSnapshot({})).toBeNull();
  });

  it("backfills missing collections so the restore path never sees undefined", () => {
    const parsed = parseSnapshot({ v: 1 });
    expect(parsed).toEqual({
      v: 1,
      viewport: null,
      layers: [],
      sentinel2Scene: null,
      selectedFieldId: null,
      workspace: { openWidgetIds: [], pinnedWidgetIds: [], activeWidgetId: null },
    });
  });

  it("rejects a non-numeric/garbled viewport rather than feeding it to jumpTo", () => {
    expect(
      parseSnapshot({ v: 1, viewport: { longitude: "x", latitude: 1, zoom: 2 } })?.viewport,
    ).toBeNull();
    expect(parseSnapshot({ v: 1, viewport: { longitude: 1, latitude: 2 } })?.viewport).toBeNull();
    expect(
      parseSnapshot({ v: 1, viewport: { longitude: 1, latitude: 2, zoom: 3 } })?.viewport,
    ).toEqual({ longitude: 1, latitude: 2, zoom: 3 });
  });

  it("drops malformed layer entries and non-string widget ids", () => {
    const parsed = parseSnapshot({
      v: 1,
      layers: [
        null,
        "nope",
        { id: 5, label: "bad-id" },
        { id: "ok", label: "Good", visible: false, opacity: 0.5 },
        { id: "buf", label: "Buffer", source: { kind: "buffer", wkt: "POLYGON((0 0))" } },
        { id: "buf2", label: "Bad src", source: { kind: "other" } },
      ],
      workspace: { openWidgetIds: ["a", 2, null, "b"], pinnedWidgetIds: [], activeWidgetId: 7 },
    });
    expect(parsed?.layers).toEqual([
      { id: "ok", label: "Good", visible: false, opacity: 0.5 },
      {
        id: "buf",
        label: "Buffer",
        visible: true,
        source: { kind: "buffer", wkt: "POLYGON((0 0))" },
      },
      { id: "buf2", label: "Bad src", visible: true },
    ]);
    expect(parsed?.workspace.openWidgetIds).toEqual(["a", "b"]);
    expect(parsed?.workspace.activeWidgetId).toBeNull();
  });

  it("restores route and isochrone layer sources (#55)", () => {
    const line: GeoJSON.Geometry = {
      type: "LineString",
      coordinates: [
        [2.35, 48.86],
        [2.13, 48.8],
      ],
    };
    const fc: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };
    const parsed = parseSnapshot({
      v: 1,
      layers: [
        { id: "route-1", label: "Route", source: { kind: "route", geometry: line } },
        { id: "iso-1", label: "Isochrone", source: { kind: "isochrone", data: fc } },
        { id: "route-bad", label: "No geom", source: { kind: "route" } },
      ],
      workspace: { openWidgetIds: [], pinnedWidgetIds: [], activeWidgetId: null },
    });
    expect(parsed?.layers).toEqual([
      { id: "route-1", label: "Route", visible: true, source: { kind: "route", geometry: line } },
      { id: "iso-1", label: "Isochrone", visible: true, source: { kind: "isochrone", data: fc } },
      // Missing geometry → source dropped, layer kept.
      { id: "route-bad", label: "No geom", visible: true },
    ]);
  });

  it("restores aggregation layer sources and rejects malformed points (#57)", () => {
    const agg = {
      kind: "aggregation",
      aggKind: "heatmap",
      weightBy: "area",
      radius: 50,
      points: [
        [2.35, 48.86, 1],
        [2.13, 48.8, 3.5],
      ],
    };
    const parsed = parseSnapshot({
      v: 1,
      layers: [
        { id: "agg-1", label: "Heatmap", source: agg },
        // Bad point shape → source dropped, layer kept.
        {
          id: "agg-bad",
          label: "Bad pts",
          source: {
            kind: "aggregation",
            aggKind: "hexagon",
            weightBy: "count",
            radius: 1000,
            points: [[1, 2]],
          },
        },
      ],
      workspace: { openWidgetIds: [], pinnedWidgetIds: [], activeWidgetId: null },
    });
    expect(parsed?.layers).toEqual([
      { id: "agg-1", label: "Heatmap", visible: true, source: agg },
      { id: "agg-bad", label: "Bad pts", visible: true },
    ]);
  });

  it("restores field-memory layer sources and rejects incomplete ones (#65)", () => {
    const fm = {
      kind: "fieldMemory",
      artifactId: "cafe1234",
      band: "slope",
      colormap: "diverging",
      url: "/api/proxy/analytics/artifacts/cafe1234/assets/slope.tif",
    };
    const parsed = parseSnapshot({
      v: 1,
      layers: [
        { id: "fm-1", label: "Trend", source: fm },
        // Missing colormap → source dropped, layer kept.
        {
          id: "fm-bad",
          label: "No colormap",
          source: { kind: "fieldMemory", artifactId: "x", band: "slope", url: "/x" },
        },
      ],
      workspace: { openWidgetIds: [], pinnedWidgetIds: [], activeWidgetId: null },
    });
    expect(parsed?.layers).toEqual([
      { id: "fm-1", label: "Trend", visible: true, source: fm },
      { id: "fm-bad", label: "No colormap", visible: true },
    ]);
  });
});

describe("snapshotsEqual", () => {
  it("treats structurally identical snapshots as equal (dedupes writes)", () => {
    const a = buildSnapshot({ ...baseInput, openWidgetIds: ["x"] });
    const b = buildSnapshot({ ...baseInput, openWidgetIds: ["x"] });
    expect(snapshotsEqual(a, b)).toBe(true);
  });

  it("detects a changed field", () => {
    const a = buildSnapshot(baseInput);
    const b = buildSnapshot({ ...baseInput, selectedFieldId: 3 });
    expect(snapshotsEqual(a, b)).toBe(false);
  });
});

describe("isEmptySnapshot", () => {
  it("is true for a fresh conversation (camera only)", () => {
    expect(isEmptySnapshot(buildSnapshot(baseInput))).toBe(true);
  });

  it("is false once a layer or widget exists", () => {
    expect(isEmptySnapshot(buildSnapshot({ ...baseInput, openWidgetIds: ["w"] }))).toBe(false);
    expect(
      isEmptySnapshot(
        buildSnapshot({
          ...baseInput,
          layers: [{ id: "buffer-1", label: "Buffer", visible: true }],
        }),
      ),
    ).toBe(false);
  });
});
