"use client";

import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import type { ReactNode, RefObject } from "react";
import type { MapRef } from "react-map-gl/maplibre";

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

export type MapLayer = {
  id: string;
  label: string;
  visible: boolean;
};

type MapStateContextValue = {
  mapRef: RefObject<MapRef | null>;
  viewport: Viewport;
  setViewport: (next: Viewport) => void;
  features: MapFeature[];
  addFeature: (feature: MapFeature) => void;
  removeFeature: (id: string) => void;
  selectedIds: string[];
  toggleSelected: (id: string) => void;
  clearSelected: () => void;
  layers: MapLayer[];
  upsertLayer: (layer: MapLayer) => void;
  removeLayer: (id: string) => void;
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
  const [viewport, setViewport] = useState<Viewport>(DEFAULT_VIEWPORT);
  const [features, setFeatures] = useState<MapFeature[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [layers, setLayers] = useState<MapLayer[]>([]);

  const addFeature = useCallback((feature: MapFeature) => {
    setFeatures((prev) => [...prev.filter((f) => f.id !== feature.id), feature]);
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

  const upsertLayer = useCallback((layer: MapLayer) => {
    setLayers((prev) => [...prev.filter((l) => l.id !== layer.id), layer]);
  }, []);

  const removeLayer = useCallback((id: string) => {
    setLayers((prev) => prev.filter((l) => l.id !== id));
  }, []);

  const value = useMemo<MapStateContextValue>(
    () => ({
      mapRef,
      viewport,
      setViewport,
      features,
      addFeature,
      removeFeature,
      selectedIds,
      toggleSelected,
      clearSelected,
      layers,
      upsertLayer,
      removeLayer,
    }),
    [
      viewport,
      features,
      addFeature,
      removeFeature,
      selectedIds,
      toggleSelected,
      clearSelected,
      layers,
      upsertLayer,
      removeLayer,
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
