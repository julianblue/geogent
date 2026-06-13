"use client";

import { z } from "zod";
import { useAssistantTool } from "@assistant-ui/react";

import { Widget } from "@/components/assistant/widgets";
import { ToolErrorChip } from "@/components/assistant/tools/ToolErrorChip";
import {
  parseToolResult,
  type ZonalStatsResult,
} from "@/components/assistant/widgets/agriculture/shared";

/**
 * Render-only UI (Pattern C) for the SERVER-executed `zonal_stats_for_field`
 * tool. The agent runs the tool against the backend; assistant-ui surfaces the
 * call+result as a tool part so we just key a widget to the tool name and read
 * its `result`. No client execute — the work already happened on the agent.
 */
export function ZonalStatsTool() {
  useAssistantTool<Record<string, unknown>, Record<string, never>>({
    toolName: "zonal_stats_for_field",
    description: "",
    parameters: z.any(),
    execute: async () => ({}),
    render: function ZonalStatsRender({ result, status, toolCallId }) {
      if (status.type === "incomplete" && status.reason === "error") {
        return <ToolErrorChip label="Zonal stats" error={status.error} />;
      }
      const data = parseToolResult<ZonalStatsResult>(result);
      if (!data || !("stats" in data)) return null;
      return <Widget id={toolCallId} type="zonal-stats" data={data} />;
    },
  });
  return null;
}
