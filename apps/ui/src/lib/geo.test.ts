import { describe, expect, it } from "vitest";

import { geometryCentroid } from "@/lib/geo";

describe("geometryCentroid", () => {
  it("returns a Point's own coordinates", () => {
    expect(geometryCentroid({ type: "Point", coordinates: [2.35, 48.86] })).toEqual([2.35, 48.86]);
  });

  it("averages a polygon ring's vertices", () => {
    const square: GeoJSON.Polygon = {
      type: "Polygon",
      coordinates: [
        [
          [0, 0],
          [2, 0],
          [2, 2],
          [0, 2],
          [0, 0],
        ],
      ],
    };
    const c = geometryCentroid(square);
    expect(c).not.toBeNull();
    expect(c![0]).toBeCloseTo(0.8, 5); // mean of 0,2,2,0,0
    expect(c![1]).toBeCloseTo(0.8, 5);
  });

  it("handles MultiPolygon by visiting all coordinates", () => {
    const mp: GeoJSON.MultiPolygon = {
      type: "MultiPolygon",
      coordinates: [
        [
          [
            [0, 0],
            [0, 0],
          ],
        ],
        [
          [
            [4, 4],
            [4, 4],
          ],
        ],
      ],
    };
    expect(geometryCentroid(mp)).toEqual([2, 2]);
  });

  it("returns null for an empty geometry", () => {
    expect(geometryCentroid({ type: "Polygon", coordinates: [] })).toBeNull();
  });
});
