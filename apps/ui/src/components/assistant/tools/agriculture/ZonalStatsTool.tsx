"use client";

import { makeAssistantToolUI } from "@assistant-ui/react";

import { Widget } from "@/components/assistant/widgets";
import { ToolErrorChip } from "@/components/assistant/tools/ToolErrorChip";
import type { ZonalStatsResult } from "@/components/assistant/widgets/agriculture/shared";

/**
 * Render-only UI (#24) for the SERVER-executed `zonal_stats_for_field` tool. The
 * agent runs the tool against the backend; assistant-ui surfaces the call+result
 * as a tool part (same path that drives ToolFallback), so we just key a widget
 * to the tool name and read its `result`. No client `execute` — the work already
 * happened on the agent.
 */
export const ZonalStatsTool = makeAssistantToolUI<Record<string, unknown>, ZonalStatsResult>({
  toolName: "zonal_stats_for_field",
  render: function ZonalStatsRender({ result, status, toolCallId }) {
    if (status.type === "incomplete" && status.reason === "error") {
      return <ToolErrorChip label="Zonal stats" error={status.error} />;
    }
    if (!result || typeof result !== "object" || !("stats" in result)) return null;
    return <Widget id={toolCallId} type="zonal-stats" data={result} />;
  },
});
