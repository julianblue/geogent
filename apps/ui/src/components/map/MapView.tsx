"use client";

import { useCallback } from "react";
import type { Map as MapLibreMap } from "maplibre-gl";
import Map, {
  NavigationControl,
  ScaleControl,
  type ViewStateChangeEvent,
} from "react-map-gl/maplibre";

import { useMapState } from "@/components/map/MapStateProvider";

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
  const { mapRef, viewport, setViewport } = useMapState();

  const syncFromMap = useCallback(
    (map: MapLibreMap | undefined | null) => {
      if (!map) return;
      const center = map.getCenter();
      const zoom = map.getZoom();
      const b = map.getBounds();
      setViewport({
        longitude: center.lng,
        latitude: center.lat,
        zoom,
        bounds: {
          west: b.getWest(),
          south: b.getSouth(),
          east: b.getEast(),
          north: b.getNorth(),
        },
      });
    },
    [setViewport],
  );

  return (
    <Map
      ref={mapRef}
      initialViewState={{
        longitude: viewport.longitude,
        latitude: viewport.latitude,
        zoom: viewport.zoom,
      }}
      mapStyle={OSM_STYLE}
      style={{ width: "100%", height: "100%" }}
      onLoad={() => syncFromMap(mapRef.current?.getMap())}
      onMoveEnd={(e: ViewStateChangeEvent) => syncFromMap(e.target as MapLibreMap)}
    >
      <NavigationControl position="top-left" />
      <ScaleControl position="bottom-left" />
    </Map>
  );
}
