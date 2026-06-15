"use client";

import { z } from "zod";
import { useAssistantTool, type ToolCallMessagePartProps } from "@assistant-ui/react";

import { useMapState } from "@/components/map/MapStateProvider";
import { addBufferOverlay } from "@/components/map/overlays";
import { Widget } from "@/components/assistant/widgets";
import { ToolErrorChip } from "@/components/assistant/tools/ToolErrorChip";
import { viewportToBboxWkt } from "@/lib/geo";

const bufferSchema = z.object({
  distance_meters: z.number().describe("Buffer distance in meters (> 0)."),
  geometry_wkt: z
    .string()
    .optional()
    .describe("Optional input geometry as WKT (SRID 4326). Omit to use the current viewport bbox."),
});

type BufferArgs = z.infer<typeof bufferSchema>;
type BufferResult = { buffered_wkt: string; distance_m: number; layer_id: string };

export function BufferLayerTool() {
  const { mapRef, viewport, upsertLayer } = useMapState();

  useAssistantTool<BufferArgs, BufferResult>({
    toolName: "add_buffer_layer",
    description:
      "Buffer a geometry by N meters and overlay the result on the map. Omit geometry_wkt to use the current viewport bbox.",
    parameters: bufferSchema,
    execute: async ({ distance_meters, geometry_wkt }) => {
      const wkt = geometry_wkt ?? viewportToBboxWkt(viewport);
      if (!wkt) throw new Error("Map viewport isn't ready yet — pan the map and retry.");
      const res = await fetch("/api/proxy/analytics/buffer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ geometry_wkt: wkt, distance_m: distance_meters }),
      });
      if (!res.ok) throw new Error(`Buffer failed: ${res.status}`);
      const data = (await res.json()) as { buffered_wkt: string };
      const layerId = `buffer-${Date.now()}`;
      addBufferOverlay(mapRef.current, layerId, data.buffered_wkt);
      upsertLayer({
        id: layerId,
        label: `Buffer ${distance_meters} m`,
        visible: true,
        opacity: 1,
        // Carry the geometry so the overlay can be repainted when a thread is
        // reopened (#20) — `execute` doesn't re-run on transcript replay.
        source: { kind: "buffer", wkt: data.buffered_wkt },
      });
      return { buffered_wkt: data.buffered_wkt, distance_m: distance_meters, layer_id: layerId };
    },
    render: function BufferRender({
      args,
      result,
      status,
      toolCallId,
    }: ToolCallMessagePartProps<BufferArgs, BufferResult>) {
      if (status.type === "incomplete" && status.reason === "error") {
        return <ToolErrorChip label="Buffer" error={status.error} />;
      }
      return (
        <Widget
          id={toolCallId}
          type="buffer"
          data={{
            status: status.type === "complete" ? "complete" : "running",
            distanceMeters: args?.distance_meters ?? 0,
            resultWkt: result?.buffered_wkt,
            layerId: result?.layer_id,
          }}
        />
      );
    },
  });
  return null;
}
