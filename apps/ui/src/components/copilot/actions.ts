"use client";

import { useCopilotAction } from "@copilotkit/react-core";
import type { MapRef } from "react-map-gl/maplibre";
import type { RefObject } from "react";

/**
 * Register CopilotKit actions the agent can call to manipulate the map.
 *
 * The agent can invoke `flyTo` to recenter the map after geocoding a place.
 * Extend this with more actions (add_layer, draw_polygon, etc.) as features grow.
 */
export function useMapActions(mapRef: RefObject<MapRef | null>) {
  useCopilotAction({
    name: "flyTo",
    description: "Fly the map to a longitude/latitude with an optional zoom level.",
    parameters: [
      { name: "longitude", type: "number", description: "Longitude in WGS84 degrees." },
      { name: "latitude", type: "number", description: "Latitude in WGS84 degrees." },
      {
        name: "zoom",
        type: "number",
        description: "Target zoom level (0-22). Defaults to 12.",
        required: false,
      },
    ],
    handler: ({ longitude, latitude, zoom }) => {
      mapRef.current?.flyTo({ center: [longitude, latitude], zoom: zoom ?? 12 });
      return `Flew to (${longitude}, ${latitude})`;
    },
  });
}
