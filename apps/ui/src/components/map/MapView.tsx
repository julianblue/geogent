"use client";

import { useCallback, useEffect, useMemo } from "react";
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
import { FEATURE_LAYER_IDS, FIELD_LAYER_IDS } from "@/components/map/overlays";
import { listFieldsInBbox } from "@/lib/fields";

const { fill: FEATURE_FILL, line: FEATURE_LINE, point: FEATURE_POINT } = FEATURE_LAYER_IDS;
const { fill: FIELD_FILL, line: FIELD_LINE } = FIELD_LAYER_IDS;
const POLYGON_TYPES = ["Polygon", "MultiPolygon"];
const LINE_TYPES = ["LineString", "MultiLineString"];
const POINT_TYPES = ["Point", "MultiPoint"];
// Fields sit below features so a feature drawn inside a field stays clickable.
const INTERACTIVE_FEATURE_LAYERS = [FEATURE_FILL, FEATURE_LINE, FEATURE_POINT, FIELD_FILL];
// How long after the last map move before we refetch fields for the viewport.
const FIELDS_FETCH_DEBOUNCE_MS = 250;

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
  const {
    mapRef,
    viewport,
    setViewport,
    setMapReady,
    features,
    selectedIds,
    toggleSelected,
    fields,
    setFields,
    selectedFieldId,
    selectField,
  } = useMapState();

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

  // Agricultural fields (#24) as their own selectable collection.
  const fieldCollection = useMemo<GeoJSON.FeatureCollection>(
    () => ({
      type: "FeatureCollection",
      features: fields.map((f) => ({
        type: "Feature",
        id: f.id,
        geometry: f.geometry,
        properties: { fieldId: f.id, name: f.name, selected: f.id === selectedFieldId ? 1 : 0 },
      })),
    }),
    [fields, selectedFieldId],
  );

  const onMapClick = useCallback(
    (e: MapLayerMouseEvent) => {
      // A field hit only counts when no feature is under the cursor, so feature
      // selection (the prior behaviour) always wins on overlap.
      const featureHit = e.features?.find((h) => typeof h.properties?.id === "string");
      if (featureHit) {
        toggleSelected(featureHit.properties!.id as string);
        return;
      }
      const fieldHit = e.features?.find((h) => typeof h.properties?.fieldId === "number");
      if (fieldHit) {
        const id = fieldHit.properties!.fieldId as number;
        selectField(id === selectedFieldId ? null : id);
      }
    },
    [toggleSelected, selectField, selectedFieldId],
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

  // Load fields intersecting the current viewport, debounced and abortable so
  // rapid panning doesn't stack requests or apply a stale response.
  const bounds = viewport.bounds;
  useEffect(() => {
    if (!bounds) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      void listFieldsInBbox(bounds)
        .then((rows) => {
          if (controller.signal.aborted) return;
          setFields(
            rows.map((r) => ({ id: r.id, name: r.name, crop: r.crop, geometry: r.geometry })),
          );
        })
        .catch(() => {
          // Field overlay is best-effort; a failed fetch shouldn't break the map.
        });
    }, FIELDS_FETCH_DEBOUNCE_MS);
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [bounds, setFields]);

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
      onClick={onMapClick}
    >
      <NavigationControl position="top-left" />
      <ScaleControl position="bottom-left" />

      <Source id="geogent-fields" type="geojson" data={fieldCollection}>
        <Layer
          id={FIELD_FILL}
          type="fill"
          paint={{
            "fill-color": ["case", ["==", ["get", "selected"], 1], "#16a34a", "#22c55e"],
            "fill-opacity": ["case", ["==", ["get", "selected"], 1], 0.3, 0.12],
          }}
        />
        <Layer
          id={FIELD_LINE}
          type="line"
          paint={{
            "line-color": ["case", ["==", ["get", "selected"], 1], "#15803d", "#16a34a"],
            "line-width": ["case", ["==", ["get", "selected"], 1], 2.5, 1.25],
            "line-dasharray": [2, 1],
          }}
        />
      </Source>

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
