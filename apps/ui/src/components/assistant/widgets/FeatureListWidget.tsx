"use client";

import { useMemo } from "react";
import { MapPin } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useMapState } from "@/components/map/MapStateProvider";
import type { WidgetDefinition, WidgetRenderProps } from "@/components/assistant/widgets/types";
import { BarChart, DataTable, StatTile, StatTileGrid } from "@/components/assistant/widgets/viz";

type FeatureRef = { id: number | string; name: string };

export type FeatureListWidgetData = {
  status: string;
  features?: FeatureRef[];
};

/** Shared zoom-to-feature affordance backed by MapState. */
function useZoomToFeature() {
  const { mapRef, features: known } = useMapState();
  return (id: FeatureRef["id"]) => {
    const f = known.find((x) => x.id === String(id));
    if (!f) return;
    const map = mapRef.current?.getMap();
    if (!map) return;
    if (f.geometry.type === "Point") {
      const [lng, lat] = (f.geometry as GeoJSON.Point).coordinates;
      map.flyTo({ center: [lng, lat], zoom: 14 });
    }
  };
}

function FeatureListInline({ data }: WidgetRenderProps<FeatureListWidgetData>) {
  const { status, features } = data;
  const list = features ?? [];
  const zoomTo = useZoomToFeature();

  return (
    <Card className="my-2 max-w-md border-l-4 border-l-primary">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <MapPin className="h-4 w-4" />
          Features in view{" "}
          <span className="text-xs font-normal text-muted-foreground">({list.length})</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-1">
        {status !== "complete" ? (
          <div className="text-sm italic text-muted-foreground">Searching…</div>
        ) : list.length === 0 ? (
          <div className="text-sm text-muted-foreground">No features inside the viewport.</div>
        ) : (
          <ul className="space-y-1">
            {list.map((f) => (
              <li
                key={String(f.id)}
                className="flex items-center justify-between rounded-md px-2 py-1 text-sm hover:bg-accent"
              >
                <span className="truncate">{f.name}</span>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 px-2 text-xs"
                  onClick={() => zoomTo(f.id)}
                >
                  Zoom
                </Button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function FeatureListExpanded({ data }: WidgetRenderProps<FeatureListWidgetData>) {
  const list = data.features ?? [];
  const zoomTo = useZoomToFeature();
  const { features: known } = useMapState();

  // Geometry-type distribution, joined from MapState which carries geometryType.
  const distribution = useMemo(() => {
    const counts = new Map<string, number>();
    for (const f of data.features ?? []) {
      const match = known.find((k) => k.id === String(f.id));
      const type = match?.geometryType ?? "Unknown";
      counts.set(type, (counts.get(type) ?? 0) + 1);
    }
    return [...counts.entries()].map(([label, count]) => ({ label, count }));
  }, [data.features, known]);

  return (
    <div className="space-y-6">
      <h2 className="flex items-center gap-2 text-lg font-semibold">
        <MapPin className="h-5 w-5" />
        Features in view
      </h2>

      <StatTileGrid>
        <StatTile label="Features" value={list.length} />
        <StatTile label="Geometry types" value={distribution.length} />
      </StatTileGrid>

      {distribution.length > 0 ? (
        <Card className="p-4">
          <div className="mb-2 text-sm font-medium">Geometry-type distribution</div>
          <BarChart data={distribution} xKey="label" yKey="count" height={200} multicolor />
        </Card>
      ) : null}

      <DataTable
        rows={list}
        rowKey={(f) => String(f.id)}
        empty="No features inside the viewport."
        columns={[
          { key: "name", header: "Name", cell: (f) => f.name },
          {
            key: "id",
            header: "ID",
            cell: (f) => (
              <span className="font-mono text-xs text-muted-foreground">{String(f.id)}</span>
            ),
          },
          {
            key: "actions",
            header: "",
            align: "right",
            cell: (f) => (
              <Button
                size="sm"
                variant="ghost"
                className="h-7 px-2 text-xs"
                onClick={() => zoomTo(f.id)}
              >
                Zoom
              </Button>
            ),
          },
        ]}
      />
    </div>
  );
}

export const featureListWidget: WidgetDefinition<FeatureListWidgetData> = {
  type: "feature-list",
  Inline: FeatureListInline,
  Expanded: FeatureListExpanded,
  title: (data) => `Features in view (${data.features?.length ?? 0})`,
};
