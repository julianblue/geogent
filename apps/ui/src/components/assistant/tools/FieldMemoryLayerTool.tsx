"use client";

import { z } from "zod";
import { useAssistantTool, type ToolCallMessagePartProps } from "@assistant-ui/react";

import { useMapState, type FieldMemoryBand } from "@/components/map/MapStateProvider";
import { ToolErrorChip } from "@/components/assistant/tools/ToolErrorChip";

const fieldMemorySchema = z.object({
  artifact_id: z.string().describe("Artifact id returned by field_memory_for_field."),
  band: z
    .enum(["productivity", "stability"])
    .optional()
    .describe("Which layer to display: productivity (default) or stability."),
  label: z.string().optional().describe("Optional layer label for the Layer Manager."),
});

type FieldMemoryArgs = z.infer<typeof fieldMemorySchema>;
type FieldMemoryResult = { layer_id: string; artifact_id: string; band: FieldMemoryBand };

const BAND_LABEL: Record<FieldMemoryBand, string> = {
  productivity: "Productivity",
  stability: "Stability",
};

/** Asset served through the authed REST proxy; deck.gl-geotiff fetches it
 *  same-origin (the small field COG is read whole when ranges aren't offered). */
function assetUrl(artifactId: string, band: FieldMemoryBand): string {
  return `/api/proxy/analytics/artifacts/${encodeURIComponent(artifactId)}/assets/${band}.tif`;
}

export function FieldMemoryLayerTool() {
  const { upsertLayer } = useMapState();

  useAssistantTool<FieldMemoryArgs, FieldMemoryResult>({
    toolName: "show_field_memory",
    description:
      "Render a built field-memory layer (productivity or stability) as a colored COG overlay on the map.",
    parameters: fieldMemorySchema,
    execute: async ({ artifact_id, band, label }) => {
      const resolvedBand: FieldMemoryBand = band ?? "productivity";
      // One layer per (artifact, band) so re-showing the same band updates in
      // place while the two bands can be shown side by side.
      const layerId = `fieldMemory-${artifact_id}-${resolvedBand}`;
      upsertLayer({
        id: layerId,
        label: label ?? `Field memory — ${BAND_LABEL[resolvedBand]}`,
        visible: true,
        opacity: 0.85,
        source: {
          kind: "fieldMemory",
          artifactId: artifact_id,
          band: resolvedBand,
          url: assetUrl(artifact_id, resolvedBand),
        },
      });
      return { layer_id: layerId, artifact_id, band: resolvedBand };
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
        <div className="text-xs text-muted-foreground">
          {BAND_LABEL[result.band]} layer drawn on the map.
        </div>
      );
    },
  });
  return null;
}
