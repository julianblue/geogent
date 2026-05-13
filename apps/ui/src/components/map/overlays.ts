import type { MapRef } from "react-map-gl/maplibre";

import { wktPolygonToGeoJSON } from "@/lib/geo";

/**
 * Add (or replace) a polygon overlay rendered as a fill+outline layer pair on the map.
 * The id is namespaced so we can have multiple overlays at once.
 */
export function addBufferOverlay(
  mapRef: MapRef | null,
  layerId: string,
  wkt: string,
): boolean {
  const map = mapRef?.getMap();
  if (!map) return false;
  const geojson = wktPolygonToGeoJSON(wkt);
  if (!geojson) return false;

  const sourceId = `${layerId}-source`;
  if (map.getLayer(`${layerId}-fill`)) map.removeLayer(`${layerId}-fill`);
  if (map.getLayer(`${layerId}-outline`)) map.removeLayer(`${layerId}-outline`);
  if (map.getSource(sourceId)) map.removeSource(sourceId);

  map.addSource(sourceId, {
    type: "geojson",
    data: { type: "Feature", geometry: geojson, properties: {} },
  });
  map.addLayer({
    id: `${layerId}-fill`,
    type: "fill",
    source: sourceId,
    paint: { "fill-color": "#2563eb", "fill-opacity": 0.18 },
  });
  map.addLayer({
    id: `${layerId}-outline`,
    type: "line",
    source: sourceId,
    paint: { "line-color": "#1d4ed8", "line-width": 2 },
  });
  return true;
}

export function removeOverlay(mapRef: MapRef | null, layerId: string): void {
  const map = mapRef?.getMap();
  if (!map) return;
  const sourceId = `${layerId}-source`;
  if (map.getLayer(`${layerId}-fill`)) map.removeLayer(`${layerId}-fill`);
  if (map.getLayer(`${layerId}-outline`)) map.removeLayer(`${layerId}-outline`);
  if (map.getSource(sourceId)) map.removeSource(sourceId);
}
