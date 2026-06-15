"use client";

import { useEffect, useMemo, useState } from "react";
import type { IControl } from "maplibre-gl";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { HeatmapLayer, HexagonLayer } from "@deck.gl/aggregation-layers";

import { useMapState, type MapLayer } from "@/components/map/MapStateProvider";
import { AGG_COLOR_RANGE, rgbCss, type AggregationPoint } from "@/components/map/aggregation";

type AggregationSource = Extract<MapLayer["source"], { kind: "aggregation" }>;

type AggLayer = MapLayer & { source: AggregationSource };

function isAggregationLayer(layer: MapLayer): layer is AggLayer {
  return layer.source?.kind === "aggregation";
}

/**
 * AggregationOverlay renders deck.gl analytics aggregation layers (#57) — a
 * heatmap or client-binned hexbin — for any MapState layer whose source is an
 * `aggregation`. Like Sentinel2Overlay it owns no layer state: the agent's
 * `add_aggregation_layer` tool registers a MapLayer and this overlay reacts,
 * honouring the layer's visibility/opacity/order from the Layer Manager.
 *
 * It uses its own MapboxOverlay (separate from the Sentinel-2 one) so the two
 * imagery/analytics surfaces don't fight over a single deck instance.
 */
export function AggregationOverlay() {
  const { mapRef, mapReady, layers } = useMapState();
  const [overlay, setOverlay] = useState<MapboxOverlay | null>(null);

  const aggLayers = useMemo(() => layers.filter(isAggregationLayer), [layers]);

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
    // Bottom layer = first; later layers paint on top. Mirror Layer Manager
    // order so reorder/visibility behaves like the other overlays.
    const deckLayers = aggLayers.filter((l) => l.visible).map((l) => buildDeckLayer(l, l.source));
    overlay.setProps({ layers: deckLayers });
  }, [overlay, aggLayers]);

  const legendFor = aggLayers.filter((l) => l.visible);
  if (legendFor.length === 0) return null;

  return (
    <div className="pointer-events-none absolute bottom-16 left-3 z-10 flex flex-col gap-2">
      {legendFor.map((l) => (
        <div
          key={l.id}
          className="pointer-events-auto flex flex-col gap-1 rounded-md bg-black/80 px-3 py-2 text-xs text-white"
        >
          <div className="font-medium">{l.label}</div>
          <div className="flex items-center gap-2">
            <span className="opacity-80">low</span>
            <div className="flex h-2 w-28 overflow-hidden rounded">
              {AGG_COLOR_RANGE.map((c, i) => (
                <div key={i} className="flex-1" style={{ background: rgbCss(c) }} />
              ))}
            </div>
            <span className="opacity-80">high</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function buildDeckLayer(layer: AggLayer, src: AggregationSource) {
  const opacity = layer.opacity ?? 1;
  const getPosition = (d: AggregationPoint) => [d[0], d[1]] as [number, number];
  const getWeight = (d: AggregationPoint) => d[2];

  if (src.aggKind === "heatmap") {
    return new HeatmapLayer<AggregationPoint>({
      id: layer.id,
      data: src.points,
      getPosition,
      getWeight,
      radiusPixels: src.radius,
      colorRange: AGG_COLOR_RANGE,
      opacity,
      pickable: false,
    });
  }
  return new HexagonLayer<AggregationPoint>({
    id: layer.id,
    data: src.points,
    getPosition,
    getColorWeight: getWeight,
    getElevationWeight: getWeight,
    colorAggregation: "SUM",
    radius: src.radius,
    colorRange: AGG_COLOR_RANGE,
    extruded: false,
    opacity,
    coverage: 0.9,
    pickable: false,
  });
}
