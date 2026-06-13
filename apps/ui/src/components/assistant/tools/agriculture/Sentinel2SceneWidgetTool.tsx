"use client";

import { z } from "zod";
import { useAssistantTool } from "@assistant-ui/react";

import { Widget } from "@/components/assistant/widgets";
import { ToolErrorChip } from "@/components/assistant/tools/ToolErrorChip";
import {
  parseToolResult,
  type CompositeResult,
} from "@/components/assistant/widgets/agriculture/shared";

/**
 * Render-only UI (Pattern C) for `show_sentinel2_scene`. That tool is a
 * LangGraph interrupt whose side effect (mounting the scene on the map) is owned
 * by {@link Sentinel2RenderTool}. Once the interrupt resumes, its result
 * (`{ok, item_id, datetime, cloud_cover, composite}`) persists as a normal tool
 * part — this binding draws the dual-mode composite widget from that result.
 */
export function Sentinel2SceneWidgetTool() {
  useAssistantTool<Record<string, unknown>, Record<string, never>>({
    toolName: "show_sentinel2_scene",
    description: "",
    parameters: z.any(),
    execute: async () => ({}),
    render: function Sentinel2SceneRender({ result, status, toolCallId }) {
      if (status.type === "incomplete" && status.reason === "error") {
        return <ToolErrorChip label="Sentinel-2 scene" error={status.error} />;
      }
      const data = parseToolResult<CompositeResult>(result);
      if (!data || !("ok" in data)) return null;
      return <Widget id={toolCallId} type="index-composite" data={data} />;
    },
  });
  return null;
}
