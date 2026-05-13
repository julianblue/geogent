"use client";

import { Loader2, Layers } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

type Status = "executing" | "inProgress" | "complete" | string;

export function BufferPreviewCard({
  status,
  distanceMeters,
  resultWkt,
}: {
  status: Status;
  distanceMeters: number;
  resultWkt?: string;
}) {
  const done = status === "complete";
  return (
    <Card className="my-2 max-w-md border-l-4 border-l-primary">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Layers className="h-4 w-4" />
          Buffer preview
        </CardTitle>
        {done ? (
          <Badge variant="secondary">complete</Badge>
        ) : (
          <span className="flex items-center gap-1 text-xs text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" />
            running
          </span>
        )}
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
