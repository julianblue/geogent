"use client";

import { useEffect } from "react";

import { useMapState } from "@/components/map/MapStateProvider";
import {
  applyOverlayOrder,
  setOverlayOpacity,
  setOverlayVisibility,
} from "@/components/map/overlays";

/**
 * Headless bridge: applies declarative layer state (visibility, opacity,
 * z-order) from MapStateProvider onto the imperative MapLibre overlays. Keeping
 * this in one effect lets the LayerManager mutate plain state while the map
 * stays in sync — even while the manager panel is collapsed/unmounted.
 */
export function LayerSync() {
  const { mapRef, mapReady, layers } = useMapState();

  useEffect(() => {
    if (!mapReady) return;
    for (const layer of layers) {
      setOverlayVisibility(mapRef.current, layer.id, layer.visible);
      setOverlayOpacity(mapRef.current, layer.id, layer.opacity ?? 1);
    }
    applyOverlayOrder(
      mapRef.current,
      layers.map((l) => l.id),
    );
  }, [mapRef, mapReady, layers]);

  return null;
}
