"use client";

import { z } from "zod";
import { useAssistantTool, type ToolCallMessagePartProps } from "@assistant-ui/react";

import { useMapState } from "@/components/map/MapStateProvider";
import { addRouteOverlay } from "@/components/map/overlays";
import { ToolErrorChip } from "@/components/assistant/tools/ToolErrorChip";

const routeSchema = z.object({
  origin_lon: z.number().describe("Origin longitude (degrees)."),
  origin_lat: z.number().describe("Origin latitude (degrees)."),
  dest_lon: z.number().describe("Destination longitude (degrees)."),
  dest_lat: z.number().describe("Destination latitude (degrees)."),
  profile: z
    .enum(["driving", "walking", "cycling"])
    .optional()
    .describe("Travel mode. Defaults to driving."),
  label: z.string().optional().describe("Optional layer label."),
});

type RouteArgs = z.infer<typeof routeSchema>;
type RouteResult = { layer_id: string; distance_km: number; duration_min: number };

export function RouteLayerTool() {
  const { mapRef, upsertLayer } = useMapState();

  useAssistantTool<RouteArgs, RouteResult>({
    toolName: "add_route_layer",
    description:
      "Draw a route between two points on the map. The browser computes the route server-side and renders the line.",
    parameters: routeSchema,
    execute: async ({ origin_lon, origin_lat, dest_lon, dest_lat, profile, label }) => {
      const res = await fetch("/api/proxy/routing/route", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          coordinates: [
            { longitude: origin_lon, latitude: origin_lat },
            { longitude: dest_lon, latitude: dest_lat },
          ],
          profile: profile ?? "driving",
        }),
      });
      if (!res.ok) {
        // Surface the backend's `detail` (e.g. "No route found…") so the error
        // chip is actionable rather than just a status code.
        const detail = await res
          .json()
          .then((b) => (b as { detail?: string }).detail)
          .catch(() => undefined);
        throw new Error(detail ?? `Routing failed: ${res.status}`);
      }
      const data = (await res.json()) as {
        geometry: GeoJSON.Geometry;
        distance_m: number;
        duration_s: number;
      };
      const layerId = `route-${Date.now()}`;
      addRouteOverlay(mapRef.current, layerId, data.geometry);
      upsertLayer({
        id: layerId,
        label: label ?? "Route",
        visible: true,
        opacity: 1,
        // Carry the geometry so the line repaints on thread reopen (#20).
        source: { kind: "route", geometry: data.geometry },
      });
      return {
        layer_id: layerId,
        distance_km: Math.round((data.distance_m / 1000) * 100) / 100,
        duration_min: Math.round((data.duration_s / 60) * 10) / 10,
      };
    },
    render: function RouteRender({
      result,
      status,
    }: ToolCallMessagePartProps<RouteArgs, RouteResult>) {
      if (status.type === "incomplete" && status.reason === "error") {
        return <ToolErrorChip label="Route" error={status.error} />;
      }
      if (status.type !== "complete" || !result) {
        return <div className="text-xs text-muted-foreground">Computing route…</div>;
      }
      return (
        <div className="text-xs text-muted-foreground">
          Route drawn — {result.distance_km} km, ~{result.duration_min} min.
        </div>
      );
    },
  });
  return null;
}
