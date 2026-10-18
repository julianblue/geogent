"use client";

import { z } from "zod";
import { useAssistantTool } from "@assistant-ui/react";

import { Widget } from "@/components/assistant/widgets";
import { ToolErrorChip } from "@/components/assistant/tools/ToolErrorChip";
import { parseToolResult } from "@/components/assistant/widgets/agriculture/shared";
import {
  profileToDashboard,
  type FieldEmbeddingProfileSummary,
} from "@/components/assistant/widgets/dashboard/profileToDashboard";

type FieldEmbeddingProfileResult = { summary?: FieldEmbeddingProfileSummary | null };

/**
 * Render-only UI (Pattern C) for the SERVER-executed `field_embedding_profile`
 * tool (ADR 0003). The tool's `summary` is mapped onto a `DashboardSpec` and
 * drawn through the existing dashboard widget — no dedicated widget type.
 */
export function FieldEmbeddingProfileTool() {
  useAssistantTool<Record<string, unknown>, Record<string, never>>({
    toolName: "field_embedding_profile",
    description: "",
    parameters: z.any(),
    execute: async () => ({}),
    render: function FieldEmbeddingProfileRender({ result, status, toolCallId }) {
      if (status.type === "incomplete" && status.reason === "error") {
        return <ToolErrorChip label="Embedding profile" error={status.error} />;
      }
      const data = parseToolResult<FieldEmbeddingProfileResult>(result);
      const spec = profileToDashboard(data?.summary);
      if (!spec) return null;
      return <Widget id={toolCallId} type="dashboard" data={spec} />;
    },
  });
  return null;
}
