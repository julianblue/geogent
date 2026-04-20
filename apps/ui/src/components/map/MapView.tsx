"use client";

import { useRef } from "react";
import Map, { type MapRef, NavigationControl } from "react-map-gl/maplibre";
import { useMapActions } from "@/components/copilot/actions";

const OSM_STYLE = {
  version: 8 as const,
  sources: {
    osm: {
      type: "raster" as const,
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [{ id: "osm", type: "raster" as const, source: "osm" }],
};

export function MapView() {
  const mapRef = useRef<MapRef | null>(null);
  useMapActions(mapRef);

  return (
    <Map
      ref={mapRef}
      initialViewState={{ longitude: -122.42, latitude: 37.77, zoom: 11 }}
      mapStyle={OSM_STYLE}
      style={{ width: "100%", height: "100%" }}
    >
      <NavigationControl position="top-left" />
    </Map>
  );
}
