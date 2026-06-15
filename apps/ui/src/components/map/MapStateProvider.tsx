"use client";

import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import type { ReactNode, RefObject } from "react";
import type { MapRef } from "react-map-gl/maplibre";

import type { Sentinel2Item } from "@/lib/sentinel2";
import type { CompositeId } from "@/lib/sentinel2-presets";

export type Viewport = {
  longitude: number;
  latitude: number;
  zoom: number;
  bounds: {
    west: number;
    south: number;
    east: number;
    north: number;
  } | null;
};

export type MapFeature = {
  id: string;
  name: string;
  geometryType: string;
  geometry: GeoJSON.Geometry;
};

/**
 * An agricultural field/parcel (#24). Kept separate from `features` because the
 * field-raster tools key off an integer `id`, whereas feature ids are strings;
 * conflating them would corrupt selection-as-context for ordinary features.
 */
export type MapField = {
  id: number;
  name: string;
  crop: string | null;
  geometry: GeoJSON.Geometry;
};

/**
 * How to recreate an imperative overlay for a layer when restoring a thread
 * snapshot (#20). Buffer overlays are drawn in the tool's `execute`, which does
 * not re-run on transcript replay, so the geometry has to ride along in the
 * snapshot to be repainted. (The Sentinel-2 overlay is data-driven via
 * `sentinel2Scene`, so it needs no source here.)
 */
export type LayerSource = { kind: "buffer"; wkt: string };

export type MapLayer = {
  id: string;
  label: string;
  visible: boolean;
  /** 0..1; defaults to 1 when omitted. */
  opacity?: number;
  /** Present for agent-created overlays that can be rebuilt from geometry. */
  source?: LayerSource;
};

/**
 * Currently-rendered Sentinel-2 scene + chosen band composite.
 *
 * Lives in MapStateProvider so the agent can drive it through a headless
 * tool while the in-map metadata badge still has a single source of truth.
 * Set to `null` to clear the overlay.
 */
export type Sentinel2Scene = {
  item: Sentinel2Item;
  compositeId: CompositeId;
};

type MapStateContextValue = {
  mapRef: RefObject<MapRef | null>;
  mapReady: boolean;
  setMapReady: (ready: boolean) => void;
  viewport: Viewport;
  setViewport: (next: Viewport) => void;
  features: MapFeature[];
  addFeature: (feature: MapFeature) => void;
  removeFeature: (id: string) => void;
  selectedIds: string[];
  toggleSelected: (id: string) => void;
  clearSelected: () => void;
  fields: MapField[];
  setFields: (fields: MapField[]) => void;
  selectedFieldId: number | null;
  selectField: (id: number | null) => void;
  layers: MapLayer[];
  upsertLayer: (layer: MapLayer) => void;
  removeLayer: (id: string) => void;
  /** Replace the whole layer list at once (used to restore a thread snapshot). */
  replaceLayers: (layers: MapLayer[]) => void;
  setLayerVisibility: (id: string, visible: boolean) => void;
  setLayerOpacity: (id: string, opacity: number) => void;
  /** Reorder a layer relative to its neighbours (affects map z-order). */
  moveLayer: (id: string, direction: "up" | "down") => void;
  sentinel2Scene: Sentinel2Scene | null;
  setSentinel2Scene: (scene: Sentinel2Scene | null) => void;
};

const DEFAULT_VIEWPORT: Viewport = {
  longitude: -122.42,
  latitude: 37.77,
  zoom: 11,
  bounds: null,
};

const MapStateContext = createContext<MapStateContextValue | null>(null);

export function MapStateProvider({ children }: { children: ReactNode }) {
  const mapRef = useRef<MapRef | null>(null);
  // Consumers that need the underlying MapLibre instance (overlays, controls)
  // subscribe to mapReady instead of polling mapRef — refs don't trigger
  // re-renders when their .current is populated.
  const [mapReady, setMapReady] = useState(false);
  const [viewport, setViewport] = useState<Viewport>(DEFAULT_VIEWPORT);
  const [features, setFeatures] = useState<MapFeature[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [fields, setFields] = useState<MapField[]>([]);
  const [selectedFieldId, setSelectedFieldId] = useState<number | null>(null);
  const [layers, setLayers] = useState<MapLayer[]>([]);
  const [sentinel2Scene, setSentinel2Scene] = useState<Sentinel2Scene | null>(null);

  const addFeature = useCallback((feature: MapFeature) => {
    setFeatures((prev) => {
      const idx = prev.findIndex((f) => f.id === feature.id);
      if (idx === -1) return [...prev, feature];
      const next = prev.slice();
      next[idx] = feature;
      return next;
    });
  }, []);

  const removeFeature = useCallback((id: string) => {
    setFeatures((prev) => prev.filter((f) => f.id !== id));
    setSelectedIds((prev) => prev.filter((sid) => sid !== id));
  }, []);

  const toggleSelected = useCallback((id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((sid) => sid !== id) : [...prev, id],
    );
  }, []);

  const clearSelected = useCallback(() => setSelectedIds([]), []);

  const selectField = useCallback((id: number | null) => setSelectedFieldId(id), []);

  const upsertLayer = useCallback((layer: MapLayer) => {
    setLayers((prev) => {
      const idx = prev.findIndex((l) => l.id === layer.id);
      if (idx === -1) return [...prev, layer];
      const next = prev.slice();
      next[idx] = layer;
      return next;
    });
  }, []);

  const removeLayer = useCallback((id: string) => {
    setLayers((prev) => prev.filter((l) => l.id !== id));
  }, []);

  const replaceLayers = useCallback((next: MapLayer[]) => setLayers(next), []);

  const setLayerVisibility = useCallback((id: string, visible: boolean) => {
    setLayers((prev) => prev.map((l) => (l.id === id ? { ...l, visible } : l)));
  }, []);

  const setLayerOpacity = useCallback((id: string, opacity: number) => {
    const clamped = Math.min(1, Math.max(0, opacity));
    setLayers((prev) => prev.map((l) => (l.id === id ? { ...l, opacity: clamped } : l)));
  }, []);

  const moveLayer = useCallback((id: string, direction: "up" | "down") => {
    setLayers((prev) => {
      const idx = prev.findIndex((l) => l.id === id);
      if (idx === -1) return prev;
      const swapWith = direction === "up" ? idx - 1 : idx + 1;
      if (swapWith < 0 || swapWith >= prev.length) return prev;
      const next = prev.slice();
      [next[idx], next[swapWith]] = [next[swapWith], next[idx]];
      return next;
    });
  }, []);

  const value = useMemo<MapStateContextValue>(
    () => ({
      mapRef,
      mapReady,
      setMapReady,
      viewport,
      setViewport,
      features,
      addFeature,
      removeFeature,
      selectedIds,
      toggleSelected,
      clearSelected,
      fields,
      setFields,
      selectedFieldId,
      selectField,
      layers,
      upsertLayer,
      removeLayer,
      replaceLayers,
      setLayerVisibility,
      setLayerOpacity,
      moveLayer,
      sentinel2Scene,
      setSentinel2Scene,
    }),
    [
      mapReady,
      viewport,
      features,
      addFeature,
      removeFeature,
      selectedIds,
      toggleSelected,
      clearSelected,
      fields,
      selectedFieldId,
      selectField,
      layers,
      upsertLayer,
      removeLayer,
      replaceLayers,
      setLayerVisibility,
      setLayerOpacity,
      moveLayer,
      sentinel2Scene,
    ],
  );

  return <MapStateContext.Provider value={value}>{children}</MapStateContext.Provider>;
}

export function useMapState(): MapStateContextValue {
  const ctx = useContext(MapStateContext);
  if (!ctx) {
    throw new Error("useMapState must be used inside <MapStateProvider>");
  }
  return ctx;
}
