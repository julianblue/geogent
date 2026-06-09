"use client";

import { makeAssistantToolUI } from "@assistant-ui/react";

import { Widget } from "@/components/assistant/widgets";
import { ToolErrorChip } from "@/components/assistant/tools/ToolErrorChip";
import {
  parseToolResult,
  type CompositeResult,
} from "@/components/assistant/widgets/agriculture/shared";

/**
 * Render-only UI (#24) for `show_sentinel2_scene`. That tool is a LangGraph
 * interrupt whose side effect (mounting the scene on the map) is owned by
 * {@link Sentinel2RenderTool}. Once the interrupt resumes, its result
 * (`{ok, item_id, datetime, cloud_cover, composite}`) persists as a normal tool
 * part — this binding draws the dual-mode composite widget from that result. The
 * two coexist: one does the work, the other renders the persisted provenance.
 */
export const Sentinel2SceneWidgetTool = makeAssistantToolUI<Record<string, unknown>, unknown>({
  toolName: "show_sentinel2_scene",
  render: function Sentinel2SceneRender({ result, status, toolCallId }) {
    if (status.type === "incomplete" && status.reason === "error") {
      return <ToolErrorChip label="Sentinel-2 scene" error={status.error} />;
    }
    const data = parseToolResult<CompositeResult>(result);
    if (!data || !("ok" in data)) return null;
    return <Widget id={toolCallId} type="index-composite" data={data} />;
  },
});
