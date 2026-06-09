"use client";

import { Crosshair, Image as ImageIcon, Satellite } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useMapState } from "@/components/map/MapStateProvider";
import { isCompositeId, SENTINEL2_PRESETS, type CompositeId } from "@/lib/sentinel2-presets";
import type { WidgetDefinition, WidgetRenderProps } from "@/components/assistant/widgets/types";
import {
  Provenance,
  type CompositeResult,
} from "@/components/assistant/widgets/agriculture/shared";

function compositeLabel(id: string | undefined): string {
  return SENTINEL2_PRESETS.find((p) => p.id === id)?.label ?? id ?? "Sentinel-2";
}

// Illustrative low→high gradients for the index colormaps (approximations of
// the GPU colormaps in raster-modules). RGB composites have no scalar legend.
const INDEX_LEGEND: Partial<Record<CompositeId, { gradient: string; low: string; high: string }>> =
  {
    ndvi: {
      gradient: "linear-gradient(90deg,#a16207,#fde047,#16a34a)",
      low: "bare",
      high: "dense",
    },
    ndwi: { gradient: "linear-gradient(90deg,#d6c08a,#bae6fd,#1d4ed8)", low: "dry", high: "water" },
    nbr: {
      gradient: "linear-gradient(90deg,#3f3f46,#f97316,#16a34a)",
      low: "burned",
      high: "healthy",
    },
    evi: {
      gradient: "linear-gradient(90deg,#ecfccb,#84cc16,#166534)",
      low: "sparse",
      high: "dense",
    },
  };

function IndexLegend({ composite }: { composite: string | undefined }) {
  const legend = composite && isCompositeId(composite) ? INDEX_LEGEND[composite] : undefined;
  if (!legend) return null;
  return (
    <div className="space-y-1">
      <div className="h-3 w-full rounded" style={{ background: legend.gradient }} />
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>{legend.low}</span>
        <span>{legend.high}</span>
      </div>
    </div>
  );
}

function ErrorCard({ reason }: { reason?: string }) {
  return (
    <Card className="my-2 max-w-md border-l-4 border-l-destructive">
      <CardContent className="py-3 text-sm text-muted-foreground">
        Couldn&apos;t render the scene{reason ? `: ${reason}` : "."}
      </CardContent>
    </Card>
  );
}

function CompositeInline({ data }: WidgetRenderProps<CompositeResult>) {
  if (data.ok === false) return <ErrorCard reason={data.reason} />;
  return (
    <Card className="my-2 max-w-md border-l-4 border-l-primary">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Satellite className="h-4 w-4" />
          {compositeLabel(data.composite)}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-1 text-sm text-muted-foreground">
        <div className="italic">Rendered on the map.</div>
        <Provenance sceneId={data.item_id} datetime={data.datetime} cloudCover={data.cloud_cover} />
      </CardContent>
    </Card>
  );
}

/**
 * Expanded composite view. We deliberately do NOT embed a second MapLibre canvas
 * here — the scene is already on the main map. Instead this drives the live map:
 * the composite switcher re-colours the existing scene via `setSentinel2Scene`
 * and "Zoom to scene" fits the main map to the scene bounds. The switcher
 * reflects the LIVE composite when a scene is mounted, so it never claims a
 * composite the map isn't showing.
 */
function CompositeExpanded({ data }: WidgetRenderProps<CompositeResult>) {
  const { sentinel2Scene, setSentinel2Scene, mapRef } = useMapState();
  if (data.ok === false) return <ErrorCard reason={data.reason} />;

  const liveComposite = sentinel2Scene?.compositeId;
  // Always a real preset id so the controlled <select> never gets `undefined`.
  const shownComposite = liveComposite ?? data.composite ?? SENTINEL2_PRESETS[0].id;

  function zoomToScene() {
    const bbox = sentinel2Scene?.item.bbox;
    const map = mapRef.current?.getMap();
    if (!bbox || !map) return;
    const [west, south, east, north] = bbox;
    map.fitBounds(
      [
        [west, south],
        [east, north],
      ],
      { padding: 40, duration: 600 },
    );
  }

  return (
    <div className="space-y-4">
      <h2 className="flex items-center gap-2 text-lg font-semibold">
        <ImageIcon className="h-5 w-5" />
        {compositeLabel(shownComposite)}
      </h2>

      <Card className="space-y-3 p-4">
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">Composite</span>
            <select
              value={shownComposite}
              disabled={!sentinel2Scene}
              onChange={(e) => {
                const next = e.target.value;
                if (sentinel2Scene && isCompositeId(next)) {
                  setSentinel2Scene({ ...sentinel2Scene, compositeId: next });
                }
              }}
              className="rounded border bg-background px-2 py-1 text-sm disabled:opacity-50"
            >
              {SENTINEL2_PRESETS.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
          <Button
            size="sm"
            variant="ghost"
            className="h-8 gap-1 px-2 text-xs"
            disabled={!sentinel2Scene}
            onClick={zoomToScene}
          >
            <Crosshair className="h-3.5 w-3.5" />
            Zoom to scene
          </Button>
        </div>

        <IndexLegend composite={shownComposite} />

        {!sentinel2Scene ? (
          <div className="text-xs text-muted-foreground">
            The scene is no longer on the map; switching is disabled.
          </div>
        ) : null}
      </Card>

      <Provenance sceneId={data.item_id} datetime={data.datetime} cloudCover={data.cloud_cover} />
    </div>
  );
}

export const indexCompositeWidget: WidgetDefinition<CompositeResult> = {
  type: "index-composite",
  Inline: CompositeInline,
  Expanded: CompositeExpanded,
  title: (data) => compositeLabel(data.composite),
};
