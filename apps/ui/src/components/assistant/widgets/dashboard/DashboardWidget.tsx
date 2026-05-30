"use client";

import { LayoutDashboard } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { WidgetDefinition, WidgetRenderProps } from "@/components/assistant/widgets/types";
import { PanelView } from "./panels";
import type { DashboardLayout, DashboardSpec, Panel } from "./schema";

// Vetted layout templates. The agent chooses one of these by name; it never
// emits raw CSS, so any composition it produces stays on-brand and responsive.
const layoutClass: Record<DashboardLayout, string> = {
  stack: "flex flex-col gap-4",
  grid: "grid grid-cols-1 gap-4 md:grid-cols-2",
  columns: "flex flex-col gap-4 md:flex-row md:[&>*]:flex-1",
};

function PanelCard({ panel }: { panel: Panel }) {
  return (
    <Card className="p-4">
      {panel.title ? (
        <div className="mb-2 text-sm font-medium text-foreground">{panel.title}</div>
      ) : null}
      <PanelView panel={panel} />
    </Card>
  );
}

function DashboardView({ spec }: { spec: DashboardSpec }) {
  return (
    <div className={layoutClass[spec.layout ?? "stack"]}>
      {spec.panels.map((panel, i) => (
        <PanelCard key={i} panel={panel} />
      ))}
    </div>
  );
}

function DashboardInline({ data }: WidgetRenderProps<DashboardSpec>) {
  return (
    <Card className="my-2 w-full border-l-4 border-l-primary">
      <CardHeader className="flex flex-row items-center gap-2 space-y-0 pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <LayoutDashboard className="h-4 w-4" />
          {data.title ?? "Dashboard"}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <DashboardView spec={data} />
      </CardContent>
    </Card>
  );
}

function DashboardExpanded({ data }: WidgetRenderProps<DashboardSpec>) {
  return (
    <div className="space-y-4">
      <h2 className="flex items-center gap-2 text-lg font-semibold">
        <LayoutDashboard className="h-5 w-5" />
        {data.title ?? "Dashboard"}
      </h2>
      <DashboardView spec={data} />
    </div>
  );
}

/**
 * The composed-dashboard widget (ADR 0001, tier 2). Unlike the single-purpose
 * widgets, its `data` is a whole {@link DashboardSpec} the agent assembled, and
 * it fans out to the panel registry rather than rendering one fixed view.
 */
export const dashboardWidget: WidgetDefinition<DashboardSpec> = {
  type: "dashboard",
  Inline: DashboardInline,
  Expanded: DashboardExpanded,
  title: (data) => data.title ?? "Dashboard",
};
