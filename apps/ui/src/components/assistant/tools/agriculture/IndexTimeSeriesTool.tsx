"use client";

import { z } from "zod";
import { useAssistantTool } from "@assistant-ui/react";

import { Widget } from "@/components/assistant/widgets";
import { ToolErrorChip } from "@/components/assistant/tools/ToolErrorChip";
import {
  parseToolResult,
  type TimeSeriesResult,
} from "@/components/assistant/widgets/agriculture/shared";

/**
 * Render-only UI (Pattern C) for the SERVER-executed
 * `seasonal_index_time_series_for_field` tool. The tool polls a backend job and
 * may sit in `running` for a while, or fail/timeout — both are handled here.
 */
export function IndexTimeSeriesTool() {
  useAssistantTool<Record<string, unknown>, Record<string, never>>({
    toolName: "seasonal_index_time_series_for_field",
    description: "",
    parameters: z.any(),
    execute: async () => ({}),
    render: function IndexTimeSeriesRender({ result, status, toolCallId }) {
      if (status.type === "incomplete" && status.reason === "error") {
        return <ToolErrorChip label="Seasonal time-series" error={status.error} />;
      }
      const data = parseToolResult<TimeSeriesResult>(result);
      if (!data || !("points" in data)) return null;
      return <Widget id={toolCallId} type="index-time-series" data={data} />;
    },
  });
  return null;
}
