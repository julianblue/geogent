import type { MapRef } from "react-map-gl/maplibre";

import { wktPolygonToGeoJSON } from "@/lib/geo";

/** Base paint values for buffer overlays, shared by add + opacity scaling. */
const BUFFER_FILL_BASE_OPACITY = 0.18;
const BUFFER_FILL_COLOR = "#2563eb";
const BUFFER_LINE_COLOR = "#1d4ed8";

/**
 * Declarative feature layers added by MapView. Kept here so LayerSync can keep
 * them stacked above imperative buffer overlays after a reorder, and MapView
 * can reuse the same ids for its <Layer> and interactive list.
 */
export const FEATURE_LAYER_IDS = {
  fill: "geogent-features-fill",
  line: "geogent-features-line",
  point: "geogent-features-point",
} as const;

/**
 * Declarative agricultural-field layers (#24). Rendered as a fill+outline pair
 * with a selection highlight, mirroring FEATURE_LAYER_IDS so clicks can drive
 * field-selection-as-context.
 */
export const FIELD_LAYER_IDS = {
  fill: "geogent-fields-fill",
  line: "geogent-fields-line",
} as const;

/**
 * Add (or replace) a polygon overlay rendered as a fill+outline layer pair on the map.
 * The id is namespaced so we can have multiple overlays at once.
 */
export function addBufferOverlay(mapRef: MapRef | null, layerId: string, wkt: string): boolean {
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
    paint: { "fill-color": BUFFER_FILL_COLOR, "fill-opacity": BUFFER_FILL_BASE_OPACITY },
  });
  map.addLayer({
    id: `${layerId}-outline`,
    type: "line",
    source: sourceId,
    paint: { "line-color": BUFFER_LINE_COLOR, "line-width": 2 },
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

/** Show/hide a buffer overlay's fill+outline layer pair. */
export function setOverlayVisibility(
  mapRef: MapRef | null,
  layerId: string,
  visible: boolean,
): void {
  const map = mapRef?.getMap();
  if (!map) return;
  const value = visible ? "visible" : "none";
  for (const suffix of ["fill", "outline"] as const) {
    const id = `${layerId}-${suffix}`;
    if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", value);
  }
}

/** Scale a buffer overlay's opacity (relative to its base paint values). */
export function setOverlayOpacity(mapRef: MapRef | null, layerId: string, opacity: number): void {
  const map = mapRef?.getMap();
  if (!map) return;
  const clamped = Math.min(1, Math.max(0, opacity));
  if (map.getLayer(`${layerId}-fill`)) {
    map.setPaintProperty(`${layerId}-fill`, "fill-opacity", BUFFER_FILL_BASE_OPACITY * clamped);
  }
  if (map.getLayer(`${layerId}-outline`)) {
    map.setPaintProperty(`${layerId}-outline`, "line-opacity", clamped);
  }
}

/**
 * Re-stack buffer overlays to match `orderedLayerIds` (first = bottom). Moving
 * each layer to the top in order leaves the last id topmost. Layers not present
 * on the map (e.g. the deck.gl Sentinel-2 overlay) are skipped.
 */
export function applyOverlayOrder(mapRef: MapRef | null, orderedLayerIds: string[]): void {
  const map = mapRef?.getMap();
  if (!map) return;
  for (const layerId of orderedLayerIds) {
    for (const suffix of ["fill", "outline"] as const) {
      const id = `${layerId}-${suffix}`;
      if (map.getLayer(id)) map.moveLayer(id);
    }
  }
  // Keep the user's feature layers (and their selection highlight) above buffer
  // overlays, which were just re-stacked to the top.
  for (const id of Object.values(FEATURE_LAYER_IDS)) {
    if (map.getLayer(id)) map.moveLayer(id);
  }
}
