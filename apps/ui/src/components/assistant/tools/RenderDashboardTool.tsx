"use client";

import { z } from "zod";
import { useAssistantTool, type ToolCallMessagePartProps } from "@assistant-ui/react";

import { Widget } from "@/components/assistant/widgets";
import { ToolErrorChip } from "@/components/assistant/tools/ToolErrorChip";
import { dashboardSpecSchema } from "@/components/assistant/widgets/dashboard/schema";

const parameters = z.object({ spec: dashboardSpecSchema });
type RenderDashboardArgs = z.infer<typeof parameters>;
type RenderDashboardResult = { rendered: boolean; panel_count: number };

/**
 * Tier-2 generative UI (ADR 0001): the agent composes a dashboard spec, the
 * browser validates it and renders the panels. No side effect — the `execute`
 * just acks so the model can keep reasoning; the render path draws the widget.
 */
export function RenderDashboardTool() {
  useAssistantTool<RenderDashboardArgs, RenderDashboardResult>({
    toolName: "render_dashboard",
    description:
      "Render a composed dashboard (charts, stat tiles, histograms, tables) from a validated spec. Use after computing analytics to visualize the results together.",
    parameters,
    execute: async ({ spec }) => ({ rendered: true, panel_count: spec.panels.length }),
    render: function RenderDashboardRender({
      args,
      status,
      toolCallId,
    }: ToolCallMessagePartProps<RenderDashboardArgs, RenderDashboardResult>) {
      if (status.type === "incomplete" && status.reason === "error") {
        return <ToolErrorChip label="Dashboard" error={status.error} />;
      }
      const parsed = dashboardSpecSchema.safeParse(args?.spec);
      if (!parsed.success) {
        // Args stream in incrementally, so a partial spec is expected while the
        // call is still running — only surface a validation error once complete.
        if (status.type !== "complete") return null;
        return <ToolErrorChip label="Dashboard" error={parsed.error.message} />;
      }
      return <Widget id={toolCallId} type="dashboard" data={parsed.data} />;
    },
  });
  return null;
}
