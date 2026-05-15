"use client";

import { useEffect, useMemo, useRef } from "react";
import type { IControl } from "maplibre-gl";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { MultiCOGLayer } from "@developmentseed/deck.gl-geotiff";
import { defaultDecoderPool } from "@developmentseed/geotiff";

import { useMapState } from "@/components/map/MapStateProvider";
import type { Sentinel2BandHrefs } from "@/lib/sentinel2";
import { isCompositeId, SENTINEL2_PRESETS } from "@/lib/sentinel2-presets";

type BandKey = keyof Sentinel2BandHrefs;

/**
 * Sentinel2Overlay renders the scene currently set on `MapStateProvider`.
 *
 * It owns no state of its own — the agent's `show_sentinel2_scene` tool
 * (or any other caller that has the provider in scope) drives what shows
 * up. The component only:
 *
 *   1. Attaches a deck.gl MapboxOverlay to the MapLibre instance when the
 *      map fires `load`.
 *   2. Builds a `MultiCOGLayer` from the current scene and feeds it to the
 *      overlay, including a `onGeoTIFFLoad` callback that fits the map.
 *   3. Renders a non-interactive metadata badge (id, date, cloud) and a
 *      "Composite" dropdown that lets the user override the agent-picked
 *      preset locally without round-tripping through chat.
 */
export function Sentinel2Overlay() {
  const { mapRef, mapReady, sentinel2Scene, setSentinel2Scene } = useMapState();
  const overlayRef = useRef<MapboxOverlay | null>(null);

  const preset =
    SENTINEL2_PRESETS.find((p) => p.id === sentinel2Scene?.compositeId) ??
    SENTINEL2_PRESETS[0];

  // Lazy-construct the decoder worker pool once per mount. defaultDecoderPool
  // caches the instance internally, but useMemo keeps this side-effect-free
  // during SSR (the function reads navigator.hardwareConcurrency).
  const decoderPool = useMemo(
    () => (typeof window === "undefined" ? undefined : defaultDecoderPool()),
    [],
  );

  // Attach overlay after the map has fired `load`. mapReady comes from
  // MapStateProvider — that's the canonical signal that mapRef.current.getMap()
  // is populated and the style is loaded.
  useEffect(() => {
    if (!mapReady) return;
    const map = mapRef.current?.getMap();
    if (!map || overlayRef.current) return;

    const overlay = new MapboxOverlay({ interleaved: false, layers: [] });
    map.addControl(overlay as unknown as IControl);
    overlayRef.current = overlay;

    return () => {
      try {
        map.removeControl(overlay as unknown as IControl);
      } catch {
        // Map may already be torn down; ignore.
      }
      overlayRef.current = null;
    };
  }, [mapRef, mapReady]);

  // Drive the deck.gl layer set from MapState.
  useEffect(() => {
    const overlay = overlayRef.current;
    if (!overlay) return;
    if (!sentinel2Scene) {
      overlay.setProps({ layers: [] });
      return;
    }
    const { item } = sentinel2Scene;

    // Only load the bands this preset actually composites — fetching all six
    // unconditionally is wasteful (NDVI needs just 2). Trade-off: switching
    // to a preset that needs different bands triggers a fresh fetch instead
    // of being instant; switching within the same band set stays instant.
    const requiredBandKeys = [
      preset.composite.r,
      preset.composite.g,
      preset.composite.b,
    ].filter((b): b is BandKey => Boolean(b));
    const sources: Record<string, { url: string }> = {};
    for (const key of new Set(requiredBandKeys)) {
      sources[key] = { url: item.bands[key] };
    }

    const layer = new MultiCOGLayer({
      id: `s2-${item.id}-${preset.id}`,
      sources,
      composite: preset.composite,
      renderPipeline: preset.pipeline,
      // Saturate the HTTP/2 connection to sentinel-cogs/us-west-2. Default
      // (6) leaves bandwidth on the table once we're fetching 4+ bands ×
      // 4–9 tiles per scene.
      maxRequests: 24,
      // Move JPEG/deflate decode off the main thread. defaultDecoderPool()
      // returns a cached singleton backed by `navigator.hardwareConcurrency`
      // workers — safe to call on every render.
      pool: decoderPool,
      onGeoTIFFLoad: (_sources, { geographicBounds }) => {
        const map = mapRef.current?.getMap();
        if (!map) return;
        const { west, south, east, north } = geographicBounds;
        map.fitBounds(
          [
            [west, south],
            [east, north],
          ],
          { padding: 40, duration: 600 },
        );
      },
    });
    overlay.setProps({ layers: [layer] });
  }, [sentinel2Scene, preset, mapRef, decoderPool]);

  if (!sentinel2Scene) return null;

  const { item, compositeId } = sentinel2Scene;
  return (
    <div className="pointer-events-none absolute right-3 top-3 z-10 flex max-w-xs flex-col items-end gap-2">
      <div className="pointer-events-auto flex flex-col gap-1.5 rounded-md bg-black/80 px-3 py-2 text-xs text-white">
        <div className="font-medium">{item.id}</div>
        <div className="opacity-80">
          {item.datetime.slice(0, 10)} · {item.cloudCover.toFixed(1)}% cloud
        </div>
        <label className="flex items-center gap-2 pt-1">
          <span className="opacity-80">Composite</span>
          <select
            value={compositeId}
            onChange={(e) => {
              const next = e.target.value;
              if (isCompositeId(next)) {
                setSentinel2Scene({ ...sentinel2Scene, compositeId: next });
              }
            }}
            className="rounded bg-white/10 px-1 py-0.5 text-white"
          >
            {SENTINEL2_PRESETS.map((p) => (
              <option key={p.id} value={p.id} className="text-black">
                {p.label}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={() => setSentinel2Scene(null)}
          className="self-start text-emerald-300 hover:underline"
        >
          Clear overlay
        </button>
      </div>
    </div>
  );
}
