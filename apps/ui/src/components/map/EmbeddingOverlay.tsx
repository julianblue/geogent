"use client";

import { useEffect, useMemo, useState } from "react";
import type { IControl } from "maplibre-gl";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { COGLayer } from "@developmentseed/deck.gl-geotiff";
import { defaultDecoderPool } from "@developmentseed/geotiff";

import { useMapState, type MapLayer } from "@/components/map/MapStateProvider";

type EmbeddingSource = Extract<MapLayer["source"], { kind: "embedding" }>;
type EmbeddingLayer = MapLayer & { source: EmbeddingSource };

function isEmbeddingLayer(layer: MapLayer): layer is EmbeddingLayer {
  return layer.source?.kind === "embedding";
}

/**
 * EmbeddingOverlay renders TESSERA embedding PCA-RGB COGs (ADR 0003) for any
 * MapState layer whose source is an `embedding`. The asset is a 3-band uint8
 * RGB COG (0 = nodata), so — unlike FieldMemoryOverlay — it needs no GLSL ramp:
 * COGLayer's default pipeline draws it as-is. Colours are an arbitrary PCA
 * projection (not comparable across years), so there is no legend, just a label
 * chip. Like its siblings it owns no layer state, honours the Layer Manager's
 * visibility/opacity, and uses its own MapboxOverlay.
 */
export function EmbeddingOverlay() {
  const { mapRef, mapReady, layers } = useMapState();
  const [overlay, setOverlay] = useState<MapboxOverlay | null>(null);

  const embLayers = useMemo(() => layers.filter(isEmbeddingLayer), [layers]);

  const decoderPool = useMemo(
    () => (typeof window === "undefined" ? undefined : defaultDecoderPool()),
    [],
  );

  useEffect(() => {
    if (!mapReady) return;
    const map = mapRef.current?.getMap();
    if (!map) return;
    const next = new MapboxOverlay({ interleaved: false, layers: [] });
    map.addControl(next as unknown as IControl);
    setOverlay(next);
    return () => {
      try {
        map.removeControl(next as unknown as IControl);
      } catch {
        // Map already torn down; ignore.
      }
      setOverlay(null);
    };
  }, [mapRef, mapReady]);

  useEffect(() => {
    if (!overlay) return;
    const deckLayers = embLayers
      .filter((l) => l.visible)
      .map(
        (l) =>
          new COGLayer({
            id: l.id,
            geotiff: l.source.url,
            opacity: l.opacity ?? 1,
            pool: decoderPool,
          }),
      );
    overlay.setProps({ layers: deckLayers });
  }, [overlay, embLayers, decoderPool]);

  const visible = embLayers.filter((l) => l.visible);
  if (visible.length === 0) return null;

  return (
    <div className="pointer-events-none absolute bottom-28 left-3 z-10 flex flex-col gap-2">
      {visible.map((l) => (
        <div
          key={l.id}
          className="pointer-events-auto flex flex-col gap-0.5 rounded-md bg-black/80 px-3 py-2 text-xs text-white"
        >
          <div className="font-medium">{l.label}</div>
          <div className="opacity-80">Embedding PCA — colours not comparable across years</div>
        </div>
      ))}
    </div>
  );
}
