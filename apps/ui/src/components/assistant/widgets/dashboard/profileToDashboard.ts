import type { DashboardSpec, Panel } from "./schema";

/**
 * Compact summary of a `field_embeddings` artifact (ADR 0003), as returned by
 * the server-executed `field_embedding_profile` tool. Only the fields the
 * dashboard reads are typed; everything is optional/nullable because the
 * summary crosses a trust boundary and a year can be partially unusable.
 */
export type FieldEmbeddingProfileSummary = {
  field_id?: number;
  area_ha?: number | null;
  years?: number[];
  grid?: { resolution_m?: number } | null;
  per_year?: Array<{
    year: number;
    pixel_count?: number | null;
    heterogeneity?: number | null;
    usable?: boolean;
  }>;
  yoy?: Array<{
    from_year: number;
    to_year: number;
    cosine_distance_centred?: number | null;
    cosine_distance_raw?: number | null;
  }>;
  rotation_screen?: { valid?: boolean; min_area_ha?: number } | null;
};

const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

const fmt = (v: number | null | undefined, digits: number): string | number =>
  finite(v) ? Number(v.toFixed(digits)) : "—";

/**
 * Map a `field_embeddings` summary onto the curated {@link DashboardSpec}
 * (ADR 0001) so it renders through `<Widget type="dashboard">` — no bespoke
 * widget. Pure so it can be unit-tested. Returns `null` when the summary
 * carries nothing to show (e.g. still running, or an unrecognised shape).
 *
 * Year-over-year points that touch a year the backend flagged `usable: false`
 * (too few pixels) or that lack a finite distance are dropped from the chart
 * rather than plotted as zero; the per-year table still lists every year so the
 * gap is visible.
 */
export function profileToDashboard(
  summary: FieldEmbeddingProfileSummary | null | undefined,
): DashboardSpec | null {
  if (!summary || typeof summary !== "object") return null;
  const perYear = Array.isArray(summary.per_year) ? summary.per_year : [];
  const yoy = Array.isArray(summary.yoy) ? summary.yoy : [];
  if (perYear.length === 0 && yoy.length === 0) return null;

  const unusable = new Set(perYear.filter((p) => p.usable === false).map((p) => p.year));
  const plottable = yoy.filter((p) => !unusable.has(p.from_year) && !unusable.has(p.to_year));
  const centred = plottable.filter((p) => finite(p.cosine_distance_centred));
  const raw = plottable.filter((p) => finite(p.cosine_distance_raw));

  const meanCentred = centred.length
    ? centred.reduce((sum, p) => sum + (p.cosine_distance_centred as number), 0) / centred.length
    : null;

  // Pixel count of the best-covered usable year (the field mask is the same
  // every year; counts differ only where a year loses pixels to masking).
  const usableYears = perYear.filter((p) => p.usable !== false);
  const counts = usableYears.map((p) => p.pixel_count).filter(finite);
  const pixels = counts.length ? Math.max(...counts) : null;

  const rotation = summary.rotation_screen;
  const minArea = rotation?.min_area_ha ?? 1;
  const resolution = summary.grid?.resolution_m;

  const panels: Panel[] = [
    {
      type: "stat",
      stats: [
        {
          label: "Mean YoY change (centred)",
          value: fmt(meanCentred, 3),
          unit: "cosine dist.",
          hint:
            centred.length > 0
              ? `Across ${centred.length} year pair${centred.length === 1 ? "" : "s"}`
              : "No usable year pairs",
        },
        {
          label: "Rotation screen",
          value: rotation ? (rotation.valid ? "Valid" : "Not valid") : "—",
          hint: finite(summary.area_ha)
            ? `Field is ${summary.area_ha.toFixed(1)} ha; needs ≥ ${minArea} ha`
            : `Needs ≥ ${minArea} ha`,
        },
        {
          label: "Field pixels",
          value: pixels ?? "—",
          hint: finite(resolution) ? `${resolution} m grid` : undefined,
        },
      ],
    },
  ];

  if (centred.length > 0 || raw.length > 0) {
    const label = (p: { from_year: number; to_year: number }) => `${p.from_year}→${p.to_year}`;
    panels.push({
      type: "timeseries",
      title: "Year-over-year embedding change (cosine distance)",
      series: [
        ...(centred.length > 0
          ? [
              {
                key: "centred",
                label: "Centred",
                points: centred.map((p) => ({
                  x: label(p),
                  y: p.cosine_distance_centred as number,
                })),
              },
            ]
          : []),
        ...(raw.length > 0
          ? [
              {
                key: "raw",
                label: "Raw",
                points: raw.map((p) => ({ x: label(p), y: p.cosine_distance_raw as number })),
              },
            ]
          : []),
      ],
    });
  }

  if (perYear.length > 0) {
    panels.push({
      type: "table",
      title: "Per-year coverage",
      columns: [
        { key: "year", header: "Year" },
        { key: "pixels", header: "Pixels", align: "right" },
        { key: "heterogeneity", header: "Heterogeneity", align: "right" },
        { key: "usable", header: "Usable" },
      ],
      rows: perYear.map((p) => ({
        year: String(p.year),
        pixels: finite(p.pixel_count) ? p.pixel_count : "—",
        heterogeneity: fmt(p.heterogeneity, 3),
        usable: p.usable === false ? "No" : "Yes",
      })),
    });
  }

  const years = perYear.map((p) => p.year).filter(finite);
  const range = years.length > 0 ? ` ${Math.min(...years)}–${Math.max(...years)}` : "";
  return {
    title: `${
      summary.field_id !== undefined ? `Field ${summary.field_id}` : "Field"
    } — embedding profile${range}`,
    layout: "stack",
    panels,
  };
}
