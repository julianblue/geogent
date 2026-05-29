"use client";

import { Loader2, Layers } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { WidgetDefinition, WidgetRenderProps } from "@/components/assistant/widgets/types";

export type BufferWidgetData = {
  status: "running" | "complete" | string;
  distanceMeters: number;
  resultWkt?: string;
};

function StatusBadge({ done }: { done: boolean }) {
  return done ? (
    <Badge variant="secondary">complete</Badge>
  ) : (
    <span className="flex items-center gap-1 text-xs text-muted-foreground">
      <Loader2 className="h-3 w-3 animate-spin" />
      running
    </span>
  );
}

function BufferInline({ data }: WidgetRenderProps<BufferWidgetData>) {
  const { status, distanceMeters, resultWkt } = data;
  const done = status === "complete";
  return (
    <Card className="my-2 max-w-md border-l-4 border-l-primary">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Layers className="h-4 w-4" />
          Buffer preview
        </CardTitle>
        <StatusBadge done={done} />
      </CardHeader>
      <CardContent className="space-y-1 text-sm text-muted-foreground">
        <div>
          <span className="text-foreground">Distance:</span> {distanceMeters.toLocaleString()} m
        </div>
        {resultWkt ? (
          <div className="truncate font-mono text-xs">{resultWkt.slice(0, 96)}…</div>
        ) : (
          <div className="italic">Waiting for backend…</div>
        )}
      </CardContent>
    </Card>
  );
}

function BufferExpanded({ data }: WidgetRenderProps<BufferWidgetData>) {
  const { status, distanceMeters, resultWkt } = data;
  const done = status === "complete";
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <Layers className="h-5 w-5" />
          Buffer preview
        </h2>
        <StatusBadge done={done} />
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
        <dt className="text-muted-foreground">Distance</dt>
        <dd>{distanceMeters.toLocaleString()} m</dd>
        <dt className="text-muted-foreground">Geometry (WKT)</dt>
        <dd className="break-all font-mono text-xs">
          {resultWkt ?? <span className="italic text-muted-foreground">Waiting for backend…</span>}
        </dd>
      </dl>
    </div>
  );
}

export const bufferWidget: WidgetDefinition<BufferWidgetData> = {
  type: "buffer",
  Inline: BufferInline,
  Expanded: BufferExpanded,
  title: (data) => `Buffer ${data.distanceMeters.toLocaleString()} m`,
};
