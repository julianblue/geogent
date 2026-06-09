"use client";

import type { HistogramBin } from "@/components/assistant/widgets/viz";

/** Spectral indices the backend computes (schemas/raster.py `IndexName`). */
export type IndexName = "ndvi" | "ndwi" | "evi" | "nbr";

export const INDEX_LABEL: Record<IndexName, string> = {
  ndvi: "NDVI",
  ndwi: "NDWI",
  evi: "EVI",
  nbr: "NBR",
};

export function indexLabel(index: string): string {
  return INDEX_LABEL[index as IndexName] ?? index.toUpperCase();
}

/** Mirrors backend `SceneRef`. */
export type SceneRef = {
  id: string;
  datetime: string;
  cloud_cover: number;
  epsg?: number | null;
};

/** Mirrors backend `ZonalStats`. */
export type ZonalStats = {
  mean: number;
  min: number;
  max: number;
  std: number;
  valid_pixels: number;
  nodata_pixels: number;
};

/** Mirrors backend `Histogram` (N+1 edges for N counts). */
export type Histogram = {
  bin_edges: number[];
  counts: number[];
};

/** Mirrors backend `ZonalStatsResponse` — the `zonal_stats_for_field` result. */
export type ZonalStatsResult = {
  field_id: number;
  index: IndexName;
  scene: SceneRef;
  stats: ZonalStats;
  histogram: Histogram;
  cached?: boolean;
};

/** Mirrors backend `TimeSeriesPoint`. */
export type TimeSeriesPoint = {
  scene_id: string;
  datetime: string;
  cloud_cover: number;
  mean: number;
  min: number;
  max: number;
  std: number;
  valid_pixels: number;
};

/** Mirrors backend `TimeSeriesResultResponse` — the seasonal-series result. */
export type TimeSeriesResult = {
  job_id: string;
  status: string;
  field_id: number;
  index: IndexName;
  params?: Record<string, unknown>;
  points: TimeSeriesPoint[];
  error?: string | null;
};

/** Resumed payload of the `show_sentinel2_scene` interrupt (success case). */
export type CompositeResult = {
  ok: boolean;
  item_id?: string;
  datetime?: string;
  cloud_cover?: number;
  composite?: string;
  reason?: string;
};

/**
 * Normalise a render-only tool-UI `result` to an object.
 *
 * Server-executed LangChain tools return a dict that LangGraph serialises into
 * the `ToolMessage` content as a JSON **string**, and `@assistant-ui/react-
 * langgraph` passes that content through as `result` verbatim (no parse —
 * `convertLangChainMessages.js`, `result: message.content`). So a tool UI keyed
 * to a server tool receives a string and must parse it. Client tools
 * (`useAssistantTool`) hand back the object directly, so we accept both. Returns
 * `null` while the result is absent (tool still running) or unparseable.
 */
export function parseToolResult<T = unknown>(result: unknown): T | null {
  if (result == null) return null;
  if (typeof result === "object") return result as T;
  if (typeof result === "string") {
    try {
      return JSON.parse(result) as T;
    } catch {
      return null;
    }
  }
  return null;
}

function fmtEdge(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

/**
 * Map a backend histogram ({@link Histogram}) to the `{label,count}[]` shape the
 * viz `Histogram` primitive expects. There are N+1 `bin_edges` for N `counts`,
 * so we iterate over `counts` (never `bin_edges`) to avoid an off-by-one; each
 * bar is labelled with its `[lo–hi)` range. Falls back to bin indices if the
 * edges don't line up.
 */
export function histogramToBins(histogram: Histogram | undefined): HistogramBin[] {
  if (!histogram || !Array.isArray(histogram.counts)) return [];
  const { counts, bin_edges } = histogram;
  const edgesAligned = Array.isArray(bin_edges) && bin_edges.length === counts.length + 1;
  return counts.map((count, i) => ({
    label: edgesAligned ? `${fmtEdge(bin_edges[i])}–${fmtEdge(bin_edges[i + 1])}` : `bin ${i + 1}`,
    count,
  }));
}

/** Compact, reusable provenance line: scene id · date · cloud %. */
export function Provenance({
  sceneId,
  datetime,
  cloudCover,
  className,
}: {
  sceneId?: string;
  datetime?: string;
  cloudCover?: number;
  className?: string;
}) {
  const parts: string[] = [];
  if (sceneId) parts.push(sceneId);
  if (datetime) parts.push(datetime.slice(0, 10));
  if (typeof cloudCover === "number") parts.push(`${cloudCover.toFixed(1)}% cloud`);
  if (parts.length === 0) return null;
  return (
    <div className={`truncate font-mono text-xs text-muted-foreground ${className ?? ""}`}>
      {parts.join(" · ")}
    </div>
  );
}
