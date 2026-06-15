/**
 * Shared config for deck.gl analytics aggregation layers (#57).
 *
 * Kept framework-agnostic (no deck.gl import) so the legend widget and the
 * snapshot parser can use the types/colours without pulling the deck bundle.
 */

export type AggregationKind = "heatmap" | "hexagon";
export type AggregationWeightBy = "count" | "area";

/** A point fed into the aggregator: [lon, lat, weight]. */
export type AggregationPoint = [number, number, number];

/**
 * Sequential low→high colour ramp (viridis), as RGB triples. Perceptually
 * uniform and legible on both light and dark basemaps, so the same ramp themes
 * the hexbin fill, the heatmap gradient, and the legend.
 */
export const AGG_COLOR_RANGE: [number, number, number][] = [
  [68, 1, 84],
  [59, 82, 139],
  [33, 145, 140],
  [94, 201, 98],
  [173, 205, 24],
  [253, 231, 37],
];

export function rgbCss([r, g, b]: [number, number, number]): string {
  return `rgb(${r}, ${g}, ${b})`;
}

/** Human label for a layer, e.g. "Heatmap of 42 features". */
export function aggregationLabel(
  kind: AggregationKind,
  count: number,
  weightBy: AggregationWeightBy,
): string {
  const noun = kind === "heatmap" ? "Heatmap" : "Hexbin";
  const by = weightBy === "area" ? " by area" : "";
  return `${noun} of ${count} feature${count === 1 ? "" : "s"}${by}`;
}
