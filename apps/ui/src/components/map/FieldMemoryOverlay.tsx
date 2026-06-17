"use client";

import { useEffect, useMemo, useState } from "react";
import type { IControl } from "maplibre-gl";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { MultiCOGLayer } from "@developmentseed/deck.gl-geotiff";
import { defaultDecoderPool } from "@developmentseed/geotiff";

import { useMapState, type MapLayer } from "@/components/map/MapStateProvider";
import {
  COLORMAP_LEGENDS,
  COLORMAP_MODULES,
  DEFAULT_COLORMAP,
  PRODUCTIVITY_MODULE,
} from "@/lib/raster-modules";

type FieldMemorySource = Extract<MapLayer["source"], { kind: "fieldMemory" }>;
type FieldMemoryLayer = MapLayer & { source: FieldMemorySource };

function isFieldMemoryLayer(layer: MapLayer): layer is FieldMemoryLayer {
  return layer.source?.kind === "fieldMemory";
}

/**
 * FieldMemoryOverlay renders cube-reduction COGs (#65) — productivity,
 * stability, trend, frequency, … — for any MapState layer whose source is a
 * `fieldMemory`. The reducer output's `colormap` id selects the GLSL ramp and
 * the legend, so new reducers need no change here as long as they reuse a known
 * colormap. Like AggregationOverlay it owns no layer state and honours the
 * Layer Manager's visibility/opacity; it uses its own MapboxOverlay so it
 * doesn't fight the Sentinel-2 / aggregation deck instances.
 */
export function FieldMemoryOverlay() {
  const { mapRef, mapReady, layers } = useMapState();
  const [overlay, setOverlay] = useState<MapboxOverlay | null>(null);

  const fmLayers = useMemo(() => layers.filter(isFieldMemoryLayer), [layers]);

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
    const deckLayers = fmLayers
      .filter((l) => l.visible)
      .map(
        (l) =>
          new MultiCOGLayer({
            id: l.id,
            sources: { value: { url: l.source.url } },
            composite: { r: "value" },
            renderPipeline: [COLORMAP_MODULES[l.source.colormap] ?? PRODUCTIVITY_MODULE],
            opacity: l.opacity ?? 1,
            pool: decoderPool,
          }),
      );
    overlay.setProps({ layers: deckLayers });
  }, [overlay, fmLayers, decoderPool]);

  const visible = fmLayers.filter((l) => l.visible);
  if (visible.length === 0) return null;

  return (
    <div className="pointer-events-none absolute bottom-16 right-3 z-10 flex flex-col gap-2">
      {visible.map((l) => {
        const legend = COLORMAP_LEGENDS[l.source.colormap] ?? COLORMAP_LEGENDS[DEFAULT_COLORMAP];
        return (
          <div
            key={l.id}
            className="pointer-events-auto flex flex-col gap-1 rounded-md bg-black/80 px-3 py-2 text-xs text-white"
          >
            <div className="font-medium">{l.label}</div>
            <div className="flex items-center gap-2">
              <span className="opacity-80">{legend.low}</span>
              <div className="flex h-2 w-28 overflow-hidden rounded">
                {legend.stops.map((c, i) => (
                  <div key={i} className="flex-1" style={{ background: c }} />
                ))}
              </div>
              <span className="opacity-80">{legend.high}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
