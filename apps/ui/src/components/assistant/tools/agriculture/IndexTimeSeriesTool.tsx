"use client";

import { makeAssistantToolUI } from "@assistant-ui/react";

import { Widget } from "@/components/assistant/widgets";
import { ToolErrorChip } from "@/components/assistant/tools/ToolErrorChip";
import type { TimeSeriesResult } from "@/components/assistant/widgets/agriculture/shared";

/**
 * Render-only UI (#24) for the SERVER-executed
 * `seasonal_index_time_series_for_field` tool. The tool polls a backend job and
 * may sit in `running` for a while, or fail/timeout — both are handled here.
 */
export const IndexTimeSeriesTool = makeAssistantToolUI<Record<string, unknown>, TimeSeriesResult>({
  toolName: "seasonal_index_time_series_for_field",
  render: function IndexTimeSeriesRender({ result, status, toolCallId }) {
    if (status.type === "incomplete" && status.reason === "error") {
      return <ToolErrorChip label="Seasonal time-series" error={status.error} />;
    }
    if (!result || typeof result !== "object" || !("points" in result)) return null;
    return <Widget id={toolCallId} type="index-time-series" data={result} />;
  },
});
