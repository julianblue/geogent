/**
 * Custom GPU shader modules for Sentinel-2 band math.
 *
 * The dev-seed deck.gl-raster package ships compositing + linear-rescale +
 * library colormap primitives, but no built-in vegetation/water/burn
 * indices. These modules fill that gap.
 *
 * Each module assumes `CompositeBands` has already populated `color` with
 * the relevant band values per the preset's `composite` mapping:
 *
 *   - `color.r` ← first band listed in composite
 *   - `color.g` ← second band
 *   - `color.b` ← third band
 *
 * After the module runs, `color.rgb` is the final RGB pixel ready for the
 * fragment shader's output (no downstream Colormap module needed — each
 * index module includes its own inline colormap).
 *
 * To swap to library colormaps later, drop the inline `mix(...)` block at
 * the end of each module and append `{module: Colormap, props: {...}}` to
 * the preset's pipeline.
 */
import type { RasterModule } from "@developmentseed/deck.gl-raster/gpu-modules";

/**
 * Map a scalar in [0, 1] to a 3-stop gradient `(low → mid → high)`. Used
 * by every index module below. Pulled out into a GLSL helper so the
 * three-color ramp logic is in one place.
 */
const RAMP_HELPER = /* glsl */ `
vec3 ramp3(float t, vec3 low, vec3 mid, vec3 high) {
  t = clamp(t, 0.0, 1.0);
  return t < 0.5 ? mix(low, mid, t * 2.0) : mix(mid, high, (t - 0.5) * 2.0);
}
`;

/**
 * NDVI = (NIR - RED) / (NIR + RED). Range [-1, 1]; typical land values
 * 0.1 (bare soil) to 0.8 (dense forest). Composite: `{r: "red", g: "nir"}`.
 *
 * Colormap: brown (bare/water) → yellow (sparse) → green (dense vegetation).
 * Mirrors the RdYlGn matplotlib palette common in agronomic tooling.
 */
export const NDVI_MODULE: RasterModule = {
  module: {
    name: "ndvi",
    inject: {
      "fs:#decl": RAMP_HELPER,
      "fs:DECKGL_FILTER_COLOR": /* glsl */ `
        float red = color.r;
        float nir = color.g;
        float ndvi = (nir - red) / (nir + red + 1e-6);
        // remap [-1, 1] → [0, 1] for the color ramp
        float t = clamp(ndvi * 0.5 + 0.5, 0.0, 1.0);
        vec3 rgb = ramp3(
          t,
          vec3(0.65, 0.16, 0.16),  // brown    — bare / water
          vec3(0.99, 0.91, 0.51),  // straw    — sparse vegetation
          vec3(0.10, 0.55, 0.20)   // forest g — dense vegetation
        );
        color = vec4(rgb, 1.0);
      `,
    },
  },
};

/**
 * NDWI = (GREEN - NIR) / (GREEN + NIR). McFeeters 1996; high positive
 * values = water. Composite: `{r: "green", g: "nir"}`.
 *
 * Colormap: tan (land) → light blue → deep blue (water).
 */
export const NDWI_MODULE: RasterModule = {
  module: {
    name: "ndwi",
    inject: {
      "fs:#decl": RAMP_HELPER,
      "fs:DECKGL_FILTER_COLOR": /* glsl */ `
        float green = color.r;
        float nir = color.g;
        float ndwi = (green - nir) / (green + nir + 1e-6);
        float t = clamp(ndwi * 0.5 + 0.5, 0.0, 1.0);
        vec3 rgb = ramp3(
          t,
          vec3(0.85, 0.75, 0.60),  // tan    — dry land
          vec3(0.55, 0.78, 0.92),  // sky b  — wet / shallow
          vec3(0.06, 0.30, 0.65)   // deep b — open water
        );
        color = vec4(rgb, 1.0);
      `,
    },
  },
};

/**
 * NBR = (NIR - SWIR2) / (NIR + SWIR2). Key et al.; high values = healthy
 * vegetation, low/negative = burned. Composite: `{r: "nir", g: "swir22"}`.
 *
 * Colormap: inferno-style, dark (severely burned) → orange (recent burn)
 * → green (unburned vegetation).
 */
export const NBR_MODULE: RasterModule = {
  module: {
    name: "nbr",
    inject: {
      "fs:#decl": RAMP_HELPER,
      "fs:DECKGL_FILTER_COLOR": /* glsl */ `
        float nir = color.r;
        float swir2 = color.g;
        float nbr = (nir - swir2) / (nir + swir2 + 1e-6);
        float t = clamp(nbr * 0.5 + 0.5, 0.0, 1.0);
        vec3 rgb = ramp3(
          t,
          vec3(0.13, 0.00, 0.10),  // near-black — severe burn
          vec3(0.95, 0.55, 0.10),  // orange     — recent / partial burn
          vec3(0.18, 0.52, 0.20)   // green      — unburned vegetation
        );
        color = vec4(rgb, 1.0);
      `,
    },
  },
};

/**
 * EVI = 2.5 * (NIR - RED) / (NIR + 6*RED - 7.5*BLUE + 1). Huete et al.;
 * resistant to atmospheric / soil noise compared to NDVI, better dynamic
 * range over dense canopies. Composite: `{r: "red", g: "nir", b: "blue"}`.
 *
 * Colormap: yellow-green sequential (low → high biomass).
 */
export const EVI_MODULE: RasterModule = {
  module: {
    name: "evi",
    inject: {
      "fs:#decl": RAMP_HELPER,
      "fs:DECKGL_FILTER_COLOR": /* glsl */ `
        float red = color.r;
        float nir = color.g;
        float blue = color.b;
        // Standard EVI coefficients (L=1, C1=6, C2=7.5, G=2.5)
        float denom = nir + 6.0 * red - 7.5 * blue + 1.0;
        float evi = denom == 0.0 ? 0.0 : (2.5 * (nir - red)) / denom;
        // EVI typical land range is roughly [0, 0.6]; stretch to [0, 1]
        float t = clamp(evi / 0.6, 0.0, 1.0);
        vec3 rgb = ramp3(
          t,
          vec3(0.99, 0.99, 0.85),  // pale yellow — low biomass
          vec3(0.65, 0.85, 0.40),  // lime green  — moderate
          vec3(0.10, 0.45, 0.15)   // dark green  — dense biomass
        );
        color = vec4(rgb, 1.0);
      `,
    },
  },
};

/**
 * Field-memory PRODUCTIVITY (#65): the multi-date mean of an index loaded as a
 * single band into `color.r`. Same RdYlGn ramp as NDVI (productivity *is* a mean
 * NDVI/index), so a brown→straw→green field reads the same way a single NDVI
 * scene does. NaN marks nodata (outside the field / no valid observations) and
 * is discarded so it stays transparent. Composite: `{r: "value"}`.
 */
export const PRODUCTIVITY_MODULE: RasterModule = {
  module: {
    name: "fieldMemoryProductivity",
    inject: {
      "fs:#decl": RAMP_HELPER,
      "fs:DECKGL_FILTER_COLOR": /* glsl */ `
        float v = color.r;
        if (v != v) { discard; }  // NaN == nodata
        // remap index [-1, 1] → [0, 1] for the ramp
        float t = clamp(v * 0.5 + 0.5, 0.0, 1.0);
        vec3 rgb = ramp3(
          t,
          vec3(0.65, 0.16, 0.16),  // brown    — consistently poor
          vec3(0.99, 0.91, 0.51),  // straw    — middling
          vec3(0.10, 0.55, 0.20)   // forest g — consistently productive
        );
        color = vec4(rgb, 1.0);
      `,
    },
  },
};

/**
 * Field-memory STABILITY (#65): the temporal coefficient of variation loaded as
 * a single band into `color.r`. Low CV = consistent across the season (good),
 * high CV = erratic. Green→yellow→red so "stable" reads green and "unstable"
 * reads red — the inverse of productivity's meaning, hence its own ramp. CV is
 * stretched [0, 0.5] → [0, 1]; NaN nodata is discarded. Composite: `{r: "value"}`.
 */
export const STABILITY_MODULE: RasterModule = {
  module: {
    name: "fieldMemoryStability",
    inject: {
      "fs:#decl": RAMP_HELPER,
      "fs:DECKGL_FILTER_COLOR": /* glsl */ `
        float v = color.r;
        if (v != v) { discard; }  // NaN == nodata
        float t = clamp(v / 0.5, 0.0, 1.0);
        vec3 rgb = ramp3(
          t,
          vec3(0.10, 0.55, 0.20),  // green  — stable
          vec3(0.99, 0.91, 0.51),  // yellow — variable
          vec3(0.84, 0.19, 0.15)   // red    — unstable
        );
        color = vec4(rgb, 1.0);
      `,
    },
  },
};

/**
 * DIVERGING (#65 M1.5): a signed value centered at 0 — e.g. the trend reducer's
 * per-year slope. Red = decline, pale = no change, green = gain. Stretched
 * roughly [-0.2, +0.2]/yr → [0,1]. NaN nodata discarded. Composite: `{r: "value"}`.
 */
export const DIVERGING_MODULE: RasterModule = {
  module: {
    name: "cubeDiverging",
    inject: {
      "fs:#decl": RAMP_HELPER,
      "fs:DECKGL_FILTER_COLOR": /* glsl */ `
        float v = color.r;
        if (v != v) { discard; }  // NaN == nodata
        float t = clamp(v / 0.4 + 0.5, 0.0, 1.0);
        vec3 rgb = ramp3(
          t,
          vec3(0.84, 0.19, 0.15),  // red   — decline
          vec3(0.96, 0.96, 0.96),  // pale  — no change
          vec3(0.10, 0.55, 0.20)   // green — gain
        );
        color = vec4(rgb, 1.0);
      `,
    },
  },
};

/**
 * SEQUENTIAL (#65 M1.5): a [0,1] magnitude — e.g. the frequency reducer's
 * fraction-of-time-above-threshold. Pale → teal → deep blue. NaN discarded.
 * Composite: `{r: "value"}`.
 */
export const SEQUENTIAL_MODULE: RasterModule = {
  module: {
    name: "cubeSequential",
    inject: {
      "fs:#decl": RAMP_HELPER,
      "fs:DECKGL_FILTER_COLOR": /* glsl */ `
        float v = color.r;
        if (v != v) { discard; }  // NaN == nodata
        float t = clamp(v, 0.0, 1.0);
        vec3 rgb = ramp3(
          t,
          vec3(0.97, 0.98, 0.80),  // pale
          vec3(0.25, 0.65, 0.65),  // teal
          vec3(0.06, 0.20, 0.42)   // deep blue
        );
        color = vec4(rgb, 1.0);
      `,
    },
  },
};

/**
 * ZONES (#65 M3): a management-zone map. Unlike every other module here the
 * value is CATEGORICAL — a 1-based zone id, not a magnitude — so it gets a
 * discrete palette with no interpolation between classes. Zone 1 is always the
 * weakest ground (the backend relabels by ascending productivity), so the ramp
 * runs red → amber → green and reads the same on every field.
 * Composite: `{r: "value"}`.
 */
export const ZONES_MODULE: RasterModule = {
  module: {
    name: "managementZones",
    inject: {
      "fs:DECKGL_FILTER_COLOR": /* glsl */ `
        float v = color.r;
        if (v != v) { discard; }          // NaN == outside / unzoned
        int zone = int(floor(v + 0.5));
        if (zone < 1) { discard; }
        vec3 rgb;
        if (zone == 1)      { rgb = vec3(0.84, 0.19, 0.15); }  // weakest
        else if (zone == 2) { rgb = vec3(0.96, 0.60, 0.26); }
        else if (zone == 3) { rgb = vec3(0.99, 0.91, 0.51); }
        else if (zone == 4) { rgb = vec3(0.65, 0.79, 0.38); }
        else if (zone == 5) { rgb = vec3(0.31, 0.66, 0.29); }
        else                { rgb = vec3(0.10, 0.45, 0.20); }  // strongest
        color = vec4(rgb, 1.0);
      `,
    },
  },
};

/**
 * Colormap registry (#65 M1.5): a reducer output's `colormap` id selects the
 * GLSL ramp + the on-map legend. Adding a reducer needs no UI change if it
 * reuses one of these ids.
 */
export const COLORMAP_MODULES: Record<string, RasterModule> = {
  rdylgn: PRODUCTIVITY_MODULE,
  stability: STABILITY_MODULE,
  diverging: DIVERGING_MODULE,
  sequential: SEQUENTIAL_MODULE,
  zones: ZONES_MODULE,
};

export type ColormapLegend = { stops: string[]; low: string; high: string };

export const COLORMAP_LEGENDS: Record<string, ColormapLegend> = {
  rdylgn: {
    stops: ["rgb(166,41,41)", "rgb(252,232,130)", "rgb(26,140,51)"],
    low: "poor",
    high: "high",
  },
  stability: {
    stops: ["rgb(26,140,51)", "rgb(252,232,130)", "rgb(214,48,38)"],
    low: "stable",
    high: "unstable",
  },
  diverging: {
    stops: ["rgb(214,48,38)", "rgb(245,245,245)", "rgb(26,140,51)"],
    low: "decline",
    high: "gain",
  },
  sequential: {
    stops: ["rgb(247,250,204)", "rgb(64,166,166)", "rgb(15,51,107)"],
    low: "low",
    high: "high",
  },
  // Categorical, but the legend still reads left-to-right weakest -> strongest
  // because zone ids are assigned in that order.
  zones: {
    stops: ["rgb(214,48,38)", "rgb(252,232,130)", "rgb(26,115,51)"],
    low: "zone 1",
    high: "highest zone",
  },
};

export const DEFAULT_COLORMAP = "rdylgn";
