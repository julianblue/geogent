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
