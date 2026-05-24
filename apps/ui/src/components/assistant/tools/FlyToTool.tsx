"use client";

import { z } from "zod";
import { useAssistantTool } from "@assistant-ui/react";

import { useMapState } from "@/components/map/MapStateProvider";

const flyToSchema = z.object({
  longitude: z.number().describe("Longitude in WGS84 degrees."),
  latitude: z.number().describe("Latitude in WGS84 degrees."),
  zoom: z.number().optional().describe("Target zoom level (0-22). Defaults to 12."),
});

export function FlyToTool() {
  const { mapRef } = useMapState();
  useAssistantTool({
    toolName: "fly_to",
    description: "Pan the map to a longitude/latitude with an optional zoom level.",
    parameters: flyToSchema,
    execute: ({ longitude, latitude, zoom }) => {
      mapRef.current?.flyTo({ center: [longitude, latitude], zoom: zoom ?? 12 });
      return { flown_to: [longitude, latitude], zoom: zoom ?? 12 };
    },
    // Intentionally silent: panning the map is the only feedback needed, so we
    // suppress the generic tool fallback chip for this tool.
    render: () => null,
  });
  return null;
}
