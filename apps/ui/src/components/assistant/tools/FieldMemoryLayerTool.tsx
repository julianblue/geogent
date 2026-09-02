"use client";

import { z } from "zod";
import { useAssistantTool, type ToolCallMessagePartProps } from "@assistant-ui/react";

import { useMapState } from "@/components/map/MapStateProvider";
import { DEFAULT_COLORMAP } from "@/lib/raster-modules";
import { ToolErrorChip } from "@/components/assistant/tools/ToolErrorChip";

const fieldMemorySchema = z.object({
  artifact_id: z.string().describe("Artifact id returned by temporal_features."),
  band: z
    .string()
    .optional()
    .describe(
      "Reducer output to display — an output name from the artifact summary " +
        "(e.g. productivity, stability, slope, frequency, composite). Defaults to productivity.",
    ),
  label: z.string().optional().describe("Optional layer label for the Layer Manager."),
});

type FieldMemoryArgs = z.infer<typeof fieldMemorySchema>;
type FieldMemoryResult = { layer_id: string; artifact_id: string; band: string };

type ArtifactAsset = { role: string; key: string; colormap?: string; label?: string };

export function FieldMemoryLayerTool() {
  const { upsertLayer } = useMapState();

  useAssistantTool<FieldMemoryArgs, FieldMemoryResult>({
    toolName: "show_raster_layer",
    description:
      "Render a raster layer of a built artifact — a cube reduction (productivity, stability, trend, …) or a management-zone map — as a colored COG overlay.",
    parameters: fieldMemorySchema,
    execute: async ({ artifact_id, band, label }) => {
      const wanted = band ?? "productivity";

      // Resolve the output's asset (URL key + colormap) from the artifact, via
      // the same-origin authed proxy. The COG itself is fetched by the overlay.
      const res = await fetch(`/api/proxy/analytics/artifacts/${encodeURIComponent(artifact_id)}`);
      if (!res.ok) {
        throw new Error(`Could not load artifact ${artifact_id} (${res.status}).`);
      }
      const data = (await res.json()) as { assets?: ArtifactAsset[] };
      const asset = (data.assets ?? []).find((a) => a.role === wanted);
      if (!asset) {
        const available = (data.assets ?? []).map((a) => a.role).join(", ") || "none";
        throw new Error(`Artifact has no '${wanted}' layer. Available: ${available}.`);
      }

      const layerId = `fieldMemory-${artifact_id}-${wanted}`;
      upsertLayer({
        id: layerId,
        label: label ?? asset.label ?? `Field memory — ${wanted}`,
        visible: true,
        opacity: 0.85,
        source: {
          kind: "fieldMemory",
          artifactId: artifact_id,
          band: wanted,
          colormap: asset.colormap ?? DEFAULT_COLORMAP,
          url: `/api/proxy/analytics/artifacts/${encodeURIComponent(artifact_id)}/assets/${asset.key}`,
        },
      });
      return { layer_id: layerId, artifact_id, band: wanted };
    },
    render: function FieldMemoryRender({
      result,
      status,
    }: ToolCallMessagePartProps<FieldMemoryArgs, FieldMemoryResult>) {
      if (status.type === "incomplete" && status.reason === "error") {
        return <ToolErrorChip label="Field memory" error={status.error} />;
      }
      if (status.type !== "complete" || !result) {
        return <div className="text-xs text-muted-foreground">Rendering field memory…</div>;
      }
      return (
        <div className="text-xs text-muted-foreground">{result.band} layer drawn on the map.</div>
      );
    },
  });
  return null;
}
