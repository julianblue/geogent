"use client";

import { BarChart3 } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Histogram, StatTile, StatTileGrid } from "@/components/assistant/widgets/viz";
import type { WidgetDefinition, WidgetRenderProps } from "@/components/assistant/widgets/types";
import {
  histogramToBins,
  indexLabel,
  Provenance,
  type ZonalStatsResult,
} from "@/components/assistant/widgets/agriculture/shared";

function fmt(value: number): string {
  return value.toFixed(3);
}

function ZonalStatsInline({ data }: WidgetRenderProps<ZonalStatsResult>) {
  const { index, scene, stats } = data;
  return (
    <Card className="my-2 max-w-md border-l-4 border-l-primary">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <BarChart3 className="h-4 w-4" />
          {indexLabel(index)} — field {data.field_id}
        </CardTitle>
        {data.cached ? <Badge variant="secondary">cached</Badge> : null}
      </CardHeader>
      <CardContent className="space-y-2">
        <StatTileGrid>
          <StatTile label="Mean" value={fmt(stats.mean)} />
          <StatTile label="Min" value={fmt(stats.min)} />
          <StatTile label="Max" value={fmt(stats.max)} />
        </StatTileGrid>
        <Provenance
          sceneId={scene?.id}
          datetime={scene?.datetime}
          cloudCover={scene?.cloud_cover}
        />
      </CardContent>
    </Card>
  );
}

function ZonalStatsExpanded({ data }: WidgetRenderProps<ZonalStatsResult>) {
  const { index, scene, stats } = data;
  const bins = histogramToBins(data.histogram);
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <BarChart3 className="h-5 w-5" />
          {indexLabel(index)} zonal statistics — field {data.field_id}
        </h2>
        {data.cached ? <Badge variant="secondary">cached</Badge> : null}
      </div>

      <StatTileGrid>
        <StatTile label="Mean" value={fmt(stats.mean)} />
        <StatTile label="Min" value={fmt(stats.min)} />
        <StatTile label="Max" value={fmt(stats.max)} />
        <StatTile label="Std dev" value={fmt(stats.std)} />
        <StatTile label="Valid px" value={stats.valid_pixels.toLocaleString()} />
        <StatTile label="No-data px" value={stats.nodata_pixels.toLocaleString()} />
      </StatTileGrid>

      <Card className="p-4">
        <div className="mb-2 text-sm font-medium text-foreground">Distribution</div>
        {bins.length > 0 ? (
          <Histogram bins={bins} height={240} />
        ) : (
          <div className="text-sm text-muted-foreground">No histogram data.</div>
        )}
      </Card>

      <Provenance sceneId={scene?.id} datetime={scene?.datetime} cloudCover={scene?.cloud_cover} />
    </div>
  );
}

export const zonalStatsWidget: WidgetDefinition<ZonalStatsResult> = {
  type: "zonal-stats",
  Inline: ZonalStatsInline,
  Expanded: ZonalStatsExpanded,
  title: (data) => `${indexLabel(data.index)} stats — field ${data.field_id}`,
};
