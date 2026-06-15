"use client";

import { z } from "zod";
import { useAssistantTool, type ToolCallMessagePartProps } from "@assistant-ui/react";

import { useMapState } from "@/components/map/MapStateProvider";
import { addIsochroneOverlay } from "@/components/map/overlays";
import { ToolErrorChip } from "@/components/assistant/tools/ToolErrorChip";

const isochroneSchema = z.object({
  longitude: z.number().describe("Center longitude (degrees)."),
  latitude: z.number().describe("Center latitude (degrees)."),
  range_minutes: z
    .array(z.number())
    .optional()
    .describe("Time budgets in minutes. Defaults to [10]."),
  profile: z
    .enum(["driving", "walking", "cycling"])
    .optional()
    .describe("Travel mode. Defaults to driving."),
  label: z.string().optional().describe("Optional layer label."),
});

type IsochroneArgs = z.infer<typeof isochroneSchema>;
type IsochroneResult = { layer_id: string; range_minutes: number[] };

export function IsochroneLayerTool() {
  const { mapRef, upsertLayer } = useMapState();

  useAssistantTool<IsochroneArgs, IsochroneResult>({
    toolName: "add_isochrone_layer",
    description:
      "Draw reachability ('N-minute') polygons around a point on the map. The browser computes the isochrone server-side and renders the polygons.",
    parameters: isochroneSchema,
    execute: async ({ longitude, latitude, range_minutes, profile, label }) => {
      const ranges = range_minutes ?? [10];
      const res = await fetch("/api/proxy/routing/isochrone", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          longitude,
          latitude,
          range_minutes: ranges,
          profile: profile ?? "driving",
        }),
      });
      if (!res.ok) {
        // Surface the backend's `detail` — notably the 503 explaining that ORS
        // isn't configured — so the error chip shows the configuration hint.
        const detail = await res
          .json()
          .then((b) => (b as { detail?: string }).detail)
          .catch(() => undefined);
        throw new Error(detail ?? `Isochrone failed: ${res.status}`);
      }
      const data = (await res.json()) as { geojson: GeoJSON.FeatureCollection };
      const layerId = `isochrone-${Date.now()}`;
      addIsochroneOverlay(mapRef.current, layerId, data.geojson);
      upsertLayer({
        id: layerId,
        label: label ?? `Isochrone (${ranges.join("/")} min)`,
        visible: true,
        opacity: 1,
        // Carry the polygons so the overlay repaints on thread reopen (#20).
        source: { kind: "isochrone", data: data.geojson },
      });
      return { layer_id: layerId, range_minutes: ranges };
    },
    render: function IsochroneRender({
      result,
      status,
    }: ToolCallMessagePartProps<IsochroneArgs, IsochroneResult>) {
      if (status.type === "incomplete" && status.reason === "error") {
        return <ToolErrorChip label="Isochrone" error={status.error} />;
      }
      if (status.type !== "complete" || !result) {
        return <div className="text-xs text-muted-foreground">Computing reachable area…</div>;
      }
      return (
        <div className="text-xs text-muted-foreground">
          Reachability drawn — {result.range_minutes.join(", ")} min.
        </div>
      );
    },
  });
  return null;
}
