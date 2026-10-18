"use client";

import { z } from "zod";
import { useAssistantTool, type ToolCallMessagePartProps } from "@assistant-ui/react";

import { useMapState } from "@/components/map/MapStateProvider";
import { ToolErrorChip } from "@/components/assistant/tools/ToolErrorChip";

const embeddingSchema = z.object({
  artifact_id: z.string().describe("Artifact id returned by embedding_layer."),
  mode: z
    .literal("pca")
    .optional()
    .describe("Embedding projection to display. Only 'pca' (3-component RGB) is supported."),
  label: z.string().optional().describe("Optional layer label for the Layer Manager."),
});

type EmbeddingArgs = z.infer<typeof embeddingSchema>;
type EmbeddingResult = { layer_id: string; artifact_id: string; mode: "pca" };

type ArtifactAsset = { role: string; key: string; label?: string };
type ArtifactResponse = {
  status?: string;
  summary?: { year?: number } | null;
  assets?: ArtifactAsset[];
  error?: string | null;
};

export function EmbeddingLayerTool() {
  const { upsertLayer } = useMapState();

  useAssistantTool<EmbeddingArgs, EmbeddingResult>({
    toolName: "show_embedding_layer",
    description:
      "Render a built TESSERA embedding PCA layer (false-colour RGB COG) as an overlay on the map.",
    parameters: embeddingSchema,
    execute: async ({ artifact_id, mode, label }) => {
      const wantedMode = mode ?? "pca";

      // Resolve the asset key and calendar year from the artifact, via the
      // same-origin authed proxy. The COG itself is fetched by the overlay.
      const res = await fetch(`/api/proxy/analytics/artifacts/${encodeURIComponent(artifact_id)}`);
      if (!res.ok) {
        throw new Error(`Could not load artifact ${artifact_id} (${res.status}).`);
      }
      const data = (await res.json()) as ArtifactResponse;
      if (data.status !== "succeeded") {
        throw new Error(
          `Artifact ${artifact_id} is not ready (status: ${data.status ?? "unknown"}${
            data.error ? `, ${data.error}` : ""
          }).`,
        );
      }
      const asset = (data.assets ?? []).find((a) => a.role === "pca_rgb");
      if (!asset) {
        const available = (data.assets ?? []).map((a) => a.role).join(", ") || "none";
        throw new Error(`Artifact has no 'pca_rgb' layer. Available: ${available}.`);
      }
      const year = data.summary?.year;
      if (typeof year !== "number" || !Number.isInteger(year)) {
        throw new Error(`Artifact ${artifact_id} summary has no valid year.`);
      }

      const layerId = `embedding-${artifact_id}-${wantedMode}`;
      upsertLayer({
        id: layerId,
        label: label ?? asset.label ?? `Embedding PCA (${year})`,
        visible: true,
        opacity: 0.85,
        source: {
          kind: "embedding",
          artifactId: artifact_id,
          mode: wantedMode,
          year,
          url: `/api/proxy/analytics/artifacts/${encodeURIComponent(artifact_id)}/assets/${asset.key}`,
        },
      });
      return { layer_id: layerId, artifact_id, mode: wantedMode };
    },
    render: function EmbeddingLayerRender({
      result,
      status,
    }: ToolCallMessagePartProps<EmbeddingArgs, EmbeddingResult>) {
      if (status.type === "incomplete" && status.reason === "error") {
        return <ToolErrorChip label="Embedding layer" error={status.error} />;
      }
      if (status.type !== "complete" || !result) {
        return <div className="text-xs text-muted-foreground">Rendering embedding layer…</div>;
      }
      return (
        <div className="text-xs text-muted-foreground">
          Embedding {result.mode.toUpperCase()} layer drawn on the map.
        </div>
      );
    },
  });
  return null;
}
