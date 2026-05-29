"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, Eye, EyeOff, Layers, Satellite, Trash2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useMapState } from "@/components/map/MapStateProvider";
import { removeOverlay } from "@/components/map/overlays";

/**
 * Layer manager (#18): surfaces agent-created layers that otherwise accumulate
 * invisibly. Lists MapState layers (buffers etc.) with visibility, opacity,
 * reorder and remove, plus a row for the current Sentinel-2 scene.
 */
export function LayerManager() {
  const {
    mapRef,
    layers,
    removeLayer,
    setLayerVisibility,
    setLayerOpacity,
    moveLayer,
    sentinel2Scene,
    setSentinel2Scene,
  } = useMapState();
  const [open, setOpen] = useState(false);

  const layerCount = layers.length + (sentinel2Scene ? 1 : 0);

  function handleRemove(id: string) {
    removeOverlay(mapRef.current, id);
    removeLayer(id);
  }

  if (!open) {
    return (
      <Button
        variant="secondary"
        size="sm"
        onClick={() => setOpen(true)}
        className="absolute bottom-3 right-3 z-10 gap-2 shadow-md"
      >
        <Layers className="h-4 w-4" />
        Layers
        {layerCount > 0 ? (
          <span className="rounded-full bg-primary/15 px-1.5 text-xs">{layerCount}</span>
        ) : null}
      </Button>
    );
  }

  return (
    <div className="absolute bottom-3 right-3 z-10 w-72 rounded-lg border border-border bg-card text-card-foreground shadow-lg">
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Layers className="h-4 w-4" />
          Layers
        </div>
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setOpen(false)}>
          <X className="h-4 w-4" />
        </Button>
      </div>

      <div className="max-h-80 overflow-y-auto p-2">
        {layerCount === 0 ? (
          <div className="px-2 py-6 text-center text-sm text-muted-foreground">
            No layers yet. Ask the agent to add one.
          </div>
        ) : (
          <ul className="space-y-1">
            {layers.map((layer, idx) => (
              <li key={layer.id} className="rounded-md px-2 py-1.5 hover:bg-accent/50">
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => setLayerVisibility(layer.id, !layer.visible)}
                    aria-label={layer.visible ? "Hide layer" : "Show layer"}
                    className="text-muted-foreground hover:text-foreground"
                  >
                    {layer.visible ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
                  </button>
                  <span className="min-w-0 flex-1 truncate text-sm" title={layer.label}>
                    {layer.label}
                  </span>
                  <button
                    type="button"
                    onClick={() => moveLayer(layer.id, "up")}
                    disabled={idx === 0}
                    aria-label="Move layer up"
                    className="text-muted-foreground hover:text-foreground disabled:opacity-30"
                  >
                    <ChevronUp className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => moveLayer(layer.id, "down")}
                    disabled={idx === layers.length - 1}
                    aria-label="Move layer down"
                    className="text-muted-foreground hover:text-foreground disabled:opacity-30"
                  >
                    <ChevronDown className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => handleRemove(layer.id)}
                    aria-label="Remove layer"
                    className="text-muted-foreground hover:text-destructive"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={layer.opacity ?? 1}
                  onChange={(e) => setLayerOpacity(layer.id, Number(e.target.value))}
                  aria-label="Layer opacity"
                  disabled={!layer.visible}
                  className="mt-1.5 h-1 w-full cursor-pointer accent-primary disabled:opacity-40"
                />
              </li>
            ))}

            {sentinel2Scene ? (
              <li className="flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-accent/50">
                <Satellite className="h-4 w-4 text-muted-foreground" />
                <span className="min-w-0 flex-1 truncate text-sm" title={sentinel2Scene.item.id}>
                  {sentinel2Scene.item.id}
                </span>
                <button
                  type="button"
                  onClick={() => setSentinel2Scene(null)}
                  aria-label="Remove Sentinel-2 scene"
                  className="text-muted-foreground hover:text-destructive"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </li>
            ) : null}
          </ul>
        )}
      </div>
    </div>
  );
}
