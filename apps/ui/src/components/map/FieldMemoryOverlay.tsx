"use client";

import { useEffect, useMemo, useState } from "react";
import type { IControl } from "maplibre-gl";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { MultiCOGLayer } from "@developmentseed/deck.gl-geotiff";
import { defaultDecoderPool } from "@developmentseed/geotiff";
import type { RasterModule } from "@developmentseed/deck.gl-raster/gpu-modules";

import {
  useMapState,
  type FieldMemoryBand,
  type MapLayer,
} from "@/components/map/MapStateProvider";
import { PRODUCTIVITY_MODULE, STABILITY_MODULE } from "@/lib/raster-modules";

type FieldMemorySource = Extract<MapLayer["source"], { kind: "fieldMemory" }>;
type FieldMemoryLayer = MapLayer & { source: FieldMemorySource };

function isFieldMemoryLayer(layer: MapLayer): layer is FieldMemoryLayer {
  return layer.source?.kind === "fieldMemory";
}

const BAND_PIPELINE: Record<FieldMemoryBand, RasterModule[]> = {
  productivity: [PRODUCTIVITY_MODULE],
  stability: [STABILITY_MODULE],
};

// Three-stop legends mirroring the GLSL ramps in raster-modules.ts.
const BAND_LEGEND: Record<FieldMemoryBand, { stops: string[]; low: string; high: string }> = {
  productivity: {
    stops: ["rgb(166,41,41)", "rgb(252,232,130)", "rgb(26,140,51)"],
    low: "poor",
    high: "productive",
  },
  stability: {
    stops: ["rgb(26,140,51)", "rgb(252,232,130)", "rgb(214,48,38)"],
    low: "stable",
    high: "unstable",
  },
};

/**
 * FieldMemoryOverlay renders multi-season "field memory" COGs (#65) — the
 * per-pixel productivity or stability layer built by `field_memory_for_field`.
 * Like AggregationOverlay it owns no layer state: the `show_field_memory` tool
 * registers a `fieldMemory` MapLayer and this overlay reacts, honouring the
 * layer's visibility/opacity from the Layer Manager. Each layer is a
 * single-band float COG rendered through the band's colormap module.
 *
 * It uses its own MapboxOverlay so it doesn't fight the Sentinel-2 or
 * aggregation deck instances for control.
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
            renderPipeline: BAND_PIPELINE[l.source.band],
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
        const legend = BAND_LEGEND[l.source.band];
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
