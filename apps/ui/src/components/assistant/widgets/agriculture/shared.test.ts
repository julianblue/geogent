import { describe, expect, it } from "vitest";

import { histogramToBins, indexLabel } from "./shared";

describe("histogramToBins", () => {
  it("maps N+1 bin_edges and N counts to N labelled bars (no off-by-one)", () => {
    const bins = histogramToBins({ bin_edges: [0, 0.5, 1], counts: [10, 20] });
    expect(bins).toHaveLength(2);
    expect(bins.map((b) => b.count)).toEqual([10, 20]);
    // Iterates over counts, pairing edge[i]..edge[i+1].
    expect(bins[0].label).toBe("0–0.50");
    expect(bins[1].label).toBe("0.50–1");
  });

  it("falls back to bin indices when edges don't align with counts", () => {
    const bins = histogramToBins({ bin_edges: [0, 1], counts: [5, 6, 7] });
    expect(bins.map((b) => b.label)).toEqual(["bin 1", "bin 2", "bin 3"]);
    expect(bins.map((b) => b.count)).toEqual([5, 6, 7]);
  });

  it("returns [] for missing histogram", () => {
    expect(histogramToBins(undefined)).toEqual([]);
  });
});

describe("indexLabel", () => {
  it("uppercases known indices and falls back gracefully", () => {
    expect(indexLabel("ndvi")).toBe("NDVI");
    expect(indexLabel("evi")).toBe("EVI");
    expect(indexLabel("custom")).toBe("CUSTOM");
  });
});
