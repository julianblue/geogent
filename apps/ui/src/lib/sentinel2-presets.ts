/**
 * Pre-baked Sentinel-2 visualization presets — the single source of truth
 * for the `composite` arg of the agent's `show_sentinel2_scene` tool and
 * for the in-map composite dropdown.
 *
 * Two kinds of presets:
 *   - **RGB composites** map three bands directly into R/G/B channels and
 *     stretch the result linearly. The classic "true color / false color"
 *     interpretations.
 *   - **Indices** map two or three bands into channels, then a custom GLSL
 *     module computes a derived value (NDVI, NBR, etc.) and applies an
 *     inline three-stop colormap.
 *
 * The id values are part of the agent contract — renaming any id here
 * requires updating the agent tool's docstring as well.
 */
import {
  FilterNoDataVal,
  LinearRescale,
  type RasterModule,
} from "@developmentseed/deck.gl-raster/gpu-modules";

import type { Sentinel2BandHrefs } from "@/lib/sentinel2";
import { EVI_MODULE, NBR_MODULE, NDVI_MODULE, NDWI_MODULE } from "@/lib/raster-modules";

/** A band slot loaded onto the GPU — keys of {@link Sentinel2BandHrefs}. */
export type BandKey = keyof Sentinel2BandHrefs;

/** Closed set of valid `composite` ids — kept in sync with `SENTINEL2_PRESETS`. */
export const COMPOSITE_IDS = [
  "true-color",
  "false-color-ir",
  "agriculture",
  "burned-area",
  "ndvi",
  "ndwi",
  "nbr",
  "evi",
] as const;
export type CompositeId = (typeof COMPOSITE_IDS)[number];

export type CompositePreset = {
  id: CompositeId;
  label: string;
  /**
   * Which loaded bands feed which channel slots of `CompositeBands`. Typed as
   * `BandKey` so a typo in a preset is a compile error, not a runtime
   * `item.bands[key]` returning undefined.
   */
  composite: { r: BandKey; g?: BandKey; b?: BandKey };
  /** GLSL pipeline applied after `CompositeBands` populates `color`. */
  pipeline: RasterModule[];
};

// deck.gl-geotiff hands us raw Sentinel-2 DN values normalised by uint16 max
// (so DN 3000 ≈ 0.046). RGB stretches are hand-tuned to match the brightness
// Sentinel Hub's EO Browser produces. Indices compute on the same normalised
// values; the index formulas are dimensionless so the absolute scale only
// matters for the colormap stretch (handled inside each module).
const rgbStretch = (rescaleMax: number): RasterModule[] => [
  { module: FilterNoDataVal, props: { noDataValue: 0 } },
  { module: LinearRescale, props: { rescaleMin: 0, rescaleMax } },
];

const indexPipeline = (indexModule: RasterModule): RasterModule[] => [
  { module: FilterNoDataVal, props: { noDataValue: 0 } },
  indexModule,
];

export const SENTINEL2_PRESETS: CompositePreset[] = [
  // ── RGB composites ────────────────────────────────────────────────────
  {
    id: "true-color",
    label: "True Color",
    composite: { r: "red", g: "green", b: "blue" },
    pipeline: rgbStretch(0.05),
  },
  {
    id: "false-color-ir",
    label: "False Color (IR)",
    composite: { r: "nir", g: "red", b: "green" },
    pipeline: rgbStretch(0.08),
  },
  {
    id: "agriculture",
    label: "Agriculture",
    composite: { r: "swir16", g: "nir", b: "blue" },
    pipeline: rgbStretch(0.08),
  },
  {
    id: "burned-area",
    label: "Burned Area",
    composite: { r: "swir22", g: "swir16", b: "nir" },
    pipeline: rgbStretch(0.1),
  },
  // ── Indices (band math + inline colormap) ────────────────────────────
  {
    id: "ndvi",
    label: "NDVI (vegetation)",
    composite: { r: "red", g: "nir" },
    pipeline: indexPipeline(NDVI_MODULE),
  },
  {
    id: "ndwi",
    label: "NDWI (water)",
    composite: { r: "green", g: "nir" },
    pipeline: indexPipeline(NDWI_MODULE),
  },
  {
    id: "nbr",
    label: "NBR (burn severity)",
    composite: { r: "nir", g: "swir22" },
    pipeline: indexPipeline(NBR_MODULE),
  },
  {
    id: "evi",
    label: "EVI (biomass)",
    composite: { r: "red", g: "nir", b: "blue" },
    pipeline: indexPipeline(EVI_MODULE),
  },
];

const COMPOSITE_ID_SET: ReadonlySet<string> = new Set(COMPOSITE_IDS);

/** Type guard / narrowing helper for the agent-supplied composite arg. */
export function isCompositeId(value: unknown): value is CompositeId {
  return typeof value === "string" && COMPOSITE_ID_SET.has(value);
}
