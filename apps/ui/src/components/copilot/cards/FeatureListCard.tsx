"use client";

import { MapPin } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useMapState } from "@/components/map/MapStateProvider";

type FeatureRef = { id: number | string; name: string };

export function FeatureListCard({
  status,
  features,
}: {
  status: string;
  features?: FeatureRef[];
}) {
  const { mapRef, features: known } = useMapState();
  const list = features ?? [];

  function zoomTo(id: FeatureRef["id"]) {
    const f = known.find((x) => x.id === String(id));
    if (!f) return;
    const map = mapRef.current?.getMap();
    if (!map) return;
    if (f.geometry.type === "Point") {
      const [lng, lat] = (f.geometry as GeoJSON.Point).coordinates;
      map.flyTo({ center: [lng, lat], zoom: 14 });
    }
  }

  return (
    <Card className="my-2 max-w-md border-l-4 border-l-primary">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <MapPin className="h-4 w-4" />
          Features in view{" "}
          <span className="text-xs font-normal text-muted-foreground">
            ({list.length})
          </span>
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
