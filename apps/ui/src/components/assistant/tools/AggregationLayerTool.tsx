"use client";

import { z } from "zod";
import { useAssistantTool, type ToolCallMessagePartProps } from "@assistant-ui/react";

import { useMapState } from "@/components/map/MapStateProvider";
import {
  AGG_COLOR_RANGE,
  aggregationLabel,
  rgbCss,
  type AggregationPoint,
} from "@/components/map/aggregation";
import { geometryCentroid } from "@/lib/geo";
import { ToolErrorChip } from "@/components/assistant/tools/ToolErrorChip";

const aggregationSchema = z.object({
  kind: z.enum(["heatmap", "hexagon"]).describe("Aggregation surface: density heatmap or hexbin."),
  weight_by: z
    .enum(["count", "area"])
    .optional()
    .describe("Weight each point by 'count' (1 each) or polygon 'area'. Defaults to count."),
  radius: z
    .number()
    .optional()
    .describe(
      "Heatmap radius in pixels, or hexbin cell radius in meters. Sensible default per kind.",
    ),
  label: z.string().optional().describe("Optional layer label for the Layer Manager."),
});

type AggregationArgs = z.infer<typeof aggregationSchema>;
type AggregationResult = { layer_id: string; kind: string; point_count: number };

/** Rough planar area (deg²) of a polygon's outer ring via the shoelace formula
 *  — only used as a relative weight, so the unit doesn't matter. */
function ringArea(geometry: GeoJSON.Geometry): number {
  if (geometry.type !== "Polygon" && geometry.type !== "MultiPolygon") return 1;
  const polys = geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;
  let total = 0;
  for (const poly of polys) {
    const ring = poly[0] ?? [];
    let a = 0;
    for (let i = 0; i < ring.length - 1; i++) {
      a += ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1];
    }
    total += Math.abs(a) / 2;
  }
  return total > 0 ? total : 1;
}

export function AggregationLayerTool() {
  const { features, fields, upsertLayer } = useMapState();

  useAssistantTool<AggregationArgs, AggregationResult>({
    toolName: "add_aggregation_layer",
    description:
      "Aggregate the current feature/field set into a deck.gl analytics surface — a density heatmap or a hexbin — and overlay it on the map.",
    parameters: aggregationSchema,
    execute: async ({ kind, weight_by, radius, label }) => {
      const weightBy = weight_by ?? "count";
      const points: AggregationPoint[] = [];
      const add = (geometry: GeoJSON.Geometry) => {
        const c = geometryCentroid(geometry);
        if (!c) return;
        points.push([c[0], c[1], weightBy === "area" ? ringArea(geometry) : 1]);
      };
      for (const f of features) add(f.geometry);
      for (const f of fields) add(f.geometry);

      if (points.length === 0) {
        throw new Error(
          "No features or fields on the map to aggregate — load or select some first.",
        );
      }

      // Heatmap radius is in pixels; hexbin radius is in meters — pick a sane
      // default per kind when the agent doesn't specify one.
      const resolvedRadius = radius ?? (kind === "heatmap" ? 50 : 1000);
      const layerId = `aggregation-${Date.now()}`;
      upsertLayer({
        id: layerId,
        label: label ?? aggregationLabel(kind, points.length, weightBy),
        visible: true,
        opacity: kind === "heatmap" ? 1 : 0.7,
        source: { kind: "aggregation", aggKind: kind, weightBy, points, radius: resolvedRadius },
      });
      return { layer_id: layerId, kind, point_count: points.length };
    },
    render: function AggregationRender({
      result,
      status,
    }: ToolCallMessagePartProps<AggregationArgs, AggregationResult>) {
      if (status.type === "incomplete" && status.reason === "error") {
        return <ToolErrorChip label="Aggregation" error={status.error} />;
      }
      if (status.type !== "complete" || !result) {
        return <div className="text-xs text-muted-foreground">Aggregating…</div>;
      }
      return (
        <div className="flex flex-col gap-1 text-xs text-muted-foreground">
          <span>
            {result.kind === "heatmap" ? "Heatmap" : "Hexbin"} of {result.point_count} feature
            {result.point_count === 1 ? "" : "s"} drawn.
          </span>
          <span className="flex items-center gap-2">
            low
            <span className="flex h-2 w-24 overflow-hidden rounded">
              {AGG_COLOR_RANGE.map((c, i) => (
                <span key={i} className="flex-1" style={{ background: rgbCss(c) }} />
              ))}
            </span>
            high
          </span>
        </div>
      );
    },
  });
  return null;
}
