"use client";

import { z } from "zod";
import { useAssistantTool, type ToolCallMessagePartProps } from "@assistant-ui/react";

import { useMapState } from "@/components/map/MapStateProvider";
import { FeatureListCard } from "@/components/copilot/cards/FeatureListCard";
import { viewportToBboxWkt } from "@/lib/geo";

type FeatureRef = { id: number | string; name: string };
type Args = Record<string, never>;
type Result = { features: FeatureRef[] };

export function FeaturesInViewportTool() {
  const { viewport } = useMapState();

  useAssistantTool<Args, Result>({
    toolName: "list_features_in_viewport",
    description: "Return features stored in the database that lie inside the current viewport.",
    parameters: z.object({}),
    execute: async () => {
      const wkt = viewportToBboxWkt(viewport);
      if (!wkt) throw new Error("Map viewport isn't ready yet — pan the map and retry.");
      const res = await fetch("/api/proxy/analytics/features-within", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ geometry_wkt: wkt }),
      });
      if (!res.ok) throw new Error(`features-within failed: ${res.status}`);
      return (await res.json()) as Result;
    },
    render: function FeaturesRender({ result, status }: ToolCallMessagePartProps<Args, Result>) {
      return (
        <FeatureListCard
          status={status.type === "complete" ? "complete" : "running"}
          features={result?.features}
        />
      );
    },
  });
  return null;
}
