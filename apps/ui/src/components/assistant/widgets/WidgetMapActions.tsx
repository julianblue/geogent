"use client";

import { Crosshair, Eye, EyeOff, Undo2 } from "lucide-react";
import type { LngLatBoundsLike } from "maplibre-gl";

import { Button } from "@/components/ui/button";
import { useMapState } from "@/components/map/MapStateProvider";
import { removeOverlay } from "@/components/map/overlays";
import { wktPolygonToGeoJSON } from "@/lib/geo";

/** Walk arbitrarily-nested GeoJSON coordinates to a [w,s,e,n] bounds. */
function geometryBounds(geometry: GeoJSON.Geometry): LngLatBoundsLike | null {
  let w = Infinity;
  let s = Infinity;
  let e = -Infinity;
  let n = -Infinity;
  const walk = (coords: unknown): void => {
    if (typeof coords === "number") return;
    if (Array.isArray(coords) && typeof coords[0] === "number") {
      const [lng, lat] = coords as number[];
      w = Math.min(w, lng);
      e = Math.max(e, lng);
      s = Math.min(s, lat);
      n = Math.max(n, lat);
      return;
    }
    if (Array.isArray(coords)) coords.forEach(walk);
  };
  if ("coordinates" in geometry) walk(geometry.coordinates);
  if (!Number.isFinite(w)) return null;
  return [
    [w, s],
    [e, n],
  ];
}

/**
 * Consistent card→map affordances for a widget that owns a map layer (#18):
 * zoom-to, toggle visibility, and remove (which doubles as undo for an
 * agent-created layer). Renders nothing once the layer is gone.
 */
export function WidgetMapActions({ layerId, zoomWkt }: { layerId: string; zoomWkt?: string }) {
  const { mapRef, layers, setLayerVisibility, removeLayer } = useMapState();
  const layer = layers.find((l) => l.id === layerId);
  if (!layer) return null;

  function zoomTo() {
    if (!zoomWkt) return;
    const geometry = wktPolygonToGeoJSON(zoomWkt);
    if (!geometry) return;
    const bounds = geometryBounds(geometry);
    if (bounds) mapRef.current?.getMap()?.fitBounds(bounds, { padding: 40, duration: 600 });
  }

  function undo() {
    removeOverlay(mapRef.current, layerId);
    removeLayer(layerId);
  }

  return (
    <div className="mt-2 flex items-center gap-1">
      {zoomWkt ? (
        <Button size="sm" variant="ghost" className="h-7 gap-1 px-2 text-xs" onClick={zoomTo}>
          <Crosshair className="h-3.5 w-3.5" />
          Zoom
        </Button>
      ) : null}
      <Button
        size="sm"
        variant="ghost"
        className="h-7 gap-1 px-2 text-xs"
        onClick={() => setLayerVisibility(layerId, !layer.visible)}
      >
        {layer.visible ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
        {layer.visible ? "Hide" : "Show"}
      </Button>
      <Button
        size="sm"
        variant="ghost"
        className="h-7 gap-1 px-2 text-xs text-muted-foreground hover:text-destructive"
        onClick={undo}
      >
        <Undo2 className="h-3.5 w-3.5" />
        Undo
      </Button>
    </div>
  );
}
