"use client";

import { useCallback, useMemo } from "react";
import type { Map as MapLibreMap } from "maplibre-gl";
import Map, {
  Layer,
  NavigationControl,
  ScaleControl,
  Source,
  type MapLayerMouseEvent,
  type MapRef,
  type ViewStateChangeEvent,
} from "react-map-gl/maplibre";
import type { Ref } from "react";

import { useMapState } from "@/components/map/MapStateProvider";
import { FEATURE_LAYER_IDS } from "@/components/map/overlays";

const { fill: FEATURE_FILL, line: FEATURE_LINE, point: FEATURE_POINT } = FEATURE_LAYER_IDS;
const POLYGON_TYPES = ["Polygon", "MultiPolygon"];
const LINE_TYPES = ["LineString", "MultiLineString"];
const POINT_TYPES = ["Point", "MultiPoint"];
// Lines and fills/points are all clickable for selection.
const INTERACTIVE_FEATURE_LAYERS = [FEATURE_FILL, FEATURE_LINE, FEATURE_POINT];

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
  const { mapRef, viewport, setViewport, setMapReady, features, selectedIds, toggleSelected } =
    useMapState();

  // Stored features as a FeatureCollection so they're clickable on the map.
  // `id` is promoted to the GeoJSON feature id and selection drives a paint
  // expression below, avoiding a second source for the highlight.
  const featureCollection = useMemo<GeoJSON.FeatureCollection>(
    () => ({
      type: "FeatureCollection",
      features: features.map((f) => ({
        type: "Feature",
        id: f.id,
        geometry: f.geometry,
        properties: { id: f.id, name: f.name, selected: selectedIds.includes(f.id) ? 1 : 0 },
      })),
    }),
    [features, selectedIds],
  );

  const onFeatureClick = useCallback(
    (e: MapLayerMouseEvent) => {
      const hit = e.features?.[0];
      const id = hit?.properties?.id;
      if (typeof id === "string") toggleSelected(id);
    },
    [toggleSelected],
  );

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
      ref={mapRef as Ref<MapRef>}
      initialViewState={{
        longitude: viewport.longitude,
        latitude: viewport.latitude,
        zoom: viewport.zoom,
      }}
      mapStyle={OSM_STYLE}
      style={{ width: "100%", height: "100%" }}
      onLoad={() => {
        syncFromMap(mapRef.current?.getMap());
        setMapReady(true);
      }}
      onMoveEnd={(e: ViewStateChangeEvent) => syncFromMap(e.target as MapLibreMap)}
      interactiveLayerIds={INTERACTIVE_FEATURE_LAYERS}
      onClick={onFeatureClick}
    >
      <NavigationControl position="top-left" />
      <ScaleControl position="bottom-left" />

      <Source id="geogent-features" type="geojson" data={featureCollection}>
        <Layer
          id={FEATURE_FILL}
          type="fill"
          filter={["in", ["geometry-type"], ["literal", POLYGON_TYPES]]}
          paint={{
            "fill-color": ["case", ["==", ["get", "selected"], 1], "#f59e0b", "#2563eb"],
            "fill-opacity": ["case", ["==", ["get", "selected"], 1], 0.35, 0.15],
          }}
        />
        <Layer
          id={FEATURE_LINE}
          type="line"
          filter={["in", ["geometry-type"], ["literal", [...POLYGON_TYPES, ...LINE_TYPES]]]}
          paint={{
            "line-color": ["case", ["==", ["get", "selected"], 1], "#d97706", "#1d4ed8"],
            "line-width": ["case", ["==", ["get", "selected"], 1], 2.5, 1.5],
          }}
        />
        <Layer
          id={FEATURE_POINT}
          type="circle"
          filter={["in", ["geometry-type"], ["literal", POINT_TYPES]]}
          paint={{
            "circle-radius": ["case", ["==", ["get", "selected"], 1], 7, 5],
            "circle-color": ["case", ["==", ["get", "selected"], 1], "#f59e0b", "#2563eb"],
            "circle-stroke-color": "#ffffff",
            "circle-stroke-width": 1.5,
          }}
        />
      </Source>
    </Map>
  );
}
