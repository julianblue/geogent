"use client";

import { LineChart as LineChartIcon } from "lucide-react";
import { Line, LineChart, ResponsiveContainer } from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  DataTable,
  seriesColor,
  TimeSeriesChart,
  type Column,
} from "@/components/assistant/widgets/viz";
import type { WidgetDefinition, WidgetRenderProps } from "@/components/assistant/widgets/types";
import {
  indexLabel,
  type TimeSeriesPoint,
  type TimeSeriesResult,
} from "@/components/assistant/widgets/agriculture/shared";

type Row = { date: string; mean: number; min: number; max: number };

function toRows(points: TimeSeriesPoint[]): Row[] {
  return points.map((p) => ({
    date: p.datetime.slice(0, 10),
    mean: p.mean,
    min: p.min,
    max: p.max,
  }));
}

function dateRange(points: TimeSeriesPoint[]): string | null {
  if (points.length === 0) return null;
  const first = points[0].datetime.slice(0, 10);
  const last = points[points.length - 1].datetime.slice(0, 10);
  return first === last ? first : `${first} → ${last}`;
}

function IndexTimeSeriesInline({ data }: WidgetRenderProps<TimeSeriesResult>) {
  const points = data.points ?? [];
  const rows = toRows(points);
  const latest = points.at(-1);
  return (
    <Card className="my-2 max-w-md border-l-4 border-l-primary">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <LineChartIcon className="h-4 w-4" />
          Seasonal {indexLabel(data.index)} — field {data.field_id}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-1 text-sm text-muted-foreground">
        {rows.length > 0 ? (
          <>
            <div className="h-12">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={rows} margin={{ top: 4, right: 4, bottom: 4, left: 4 }}>
                  <Line
                    type="monotone"
                    dataKey="mean"
                    stroke={seriesColor(0)}
                    strokeWidth={1.5}
                    dot={false}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div>
              <span className="text-foreground">{points.length}</span> scenes
              {latest ? (
                <>
                  {" · latest "}
                  <span className="text-foreground">{latest.mean.toFixed(3)}</span>
                </>
              ) : null}
            </div>
          </>
        ) : (
          <div className="italic">No cloud-free scenes in range.</div>
        )}
      </CardContent>
    </Card>
  );
}

function IndexTimeSeriesExpanded({ data }: WidgetRenderProps<TimeSeriesResult>) {
  const points = data.points ?? [];
  const rows = toRows(points);
  const label = indexLabel(data.index);
  const range = dateRange(points);

  const columns: Column<TimeSeriesPoint>[] = [
    { key: "date", header: "Date", cell: (p) => p.datetime.slice(0, 10) },
    {
      key: "scene",
      header: "Scene",
      cell: (p) => <span className="font-mono text-xs">{p.scene_id}</span>,
    },
    { key: "cloud", header: "Cloud", align: "right", cell: (p) => `${p.cloud_cover.toFixed(1)}%` },
    { key: "mean", header: "Mean", align: "right", cell: (p) => p.mean.toFixed(3) },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <LineChartIcon className="h-5 w-5" />
          Seasonal {label} — field {data.field_id}
        </h2>
        {range ? <span className="text-xs text-muted-foreground">{range}</span> : null}
      </div>

      <Card className="p-4">
        {rows.length > 0 ? (
          <TimeSeriesChart
            data={rows}
            xKey="date"
            series={[
              { key: "mean", label: `Mean ${label}` },
              { key: "min", label: "Min" },
              { key: "max", label: "Max" },
            ]}
            height={260}
          />
        ) : (
          <div className="text-sm text-muted-foreground">No cloud-free scenes in range.</div>
        )}
      </Card>

      <Card className="p-4">
        <div className="mb-2 text-sm font-medium text-foreground">Scenes</div>
        <DataTable rows={points} columns={columns} rowKey={(p) => p.scene_id} empty="No scenes." />
      </Card>
    </div>
  );
}

export const indexTimeSeriesWidget: WidgetDefinition<TimeSeriesResult> = {
  type: "index-time-series",
  Inline: IndexTimeSeriesInline,
  Expanded: IndexTimeSeriesExpanded,
  title: (data) => `Seasonal ${indexLabel(data.index)} — field ${data.field_id}`,
};
