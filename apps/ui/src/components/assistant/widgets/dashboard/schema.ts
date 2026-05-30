import { z } from "zod";

/**
 * The standardized, agent-facing contract for an LLM-*composed* dashboard.
 *
 * This is the tier-2 mechanism from ADR 0001: rather than the agent picking one
 * pre-built widget, it assembles several panels into a vetted layout via the
 * `render_dashboard` tool. The browser validates the spec here (defense at the
 * trust boundary) and {@link DashboardWidget} renders each panel through the
 * shared viz primitives — so every combination looks good by construction.
 *
 * Adding a panel type is a two-step change: extend the discriminated union here,
 * then add its renderer in `panels.tsx`. Keep this in sync with the Pydantic
 * `DashboardSpec` in `apps/agent/src/geogent_agent/tools/frontend_actions.py`.
 */

const statItemSchema = z.object({
  label: z.string(),
  value: z.union([z.number(), z.string()]),
  unit: z.string().optional(),
  hint: z.string().optional(),
});

const statPanelSchema = z.object({
  type: z.literal("stat"),
  title: z.string().optional(),
  stats: z.array(statItemSchema).min(1),
});

const seriesSchema = z.object({
  key: z.string(),
  label: z.string().optional(),
  points: z.array(z.object({ x: z.string(), y: z.number() })),
});

const timeSeriesPanelSchema = z.object({
  type: z.literal("timeseries"),
  title: z.string().optional(),
  series: z.array(seriesSchema).min(1),
});

const histogramPanelSchema = z.object({
  type: z.literal("histogram"),
  title: z.string().optional(),
  bins: z.array(z.object({ label: z.string(), count: z.number() })).min(1),
});

const tablePanelSchema = z.object({
  type: z.literal("table"),
  title: z.string().optional(),
  columns: z
    .array(
      z.object({
        key: z.string(),
        header: z.string(),
        align: z.enum(["left", "right"]).optional(),
      }),
    )
    .min(1),
  rows: z.array(z.record(z.string(), z.union([z.string(), z.number()]))),
});

export const panelSchema = z.discriminatedUnion("type", [
  statPanelSchema,
  timeSeriesPanelSchema,
  histogramPanelSchema,
  tablePanelSchema,
]);

// `layout` is optional (not `.default`) so the schema's input and output types
// stay identical — assistant-ui's `parameters` type requires that. The default
// ("stack") is applied at render time in DashboardWidget.
export const dashboardSpecSchema = z.object({
  title: z.string().optional(),
  layout: z.enum(["stack", "grid", "columns"]).optional(),
  panels: z.array(panelSchema).min(1),
});

export type DashboardLayout = NonNullable<z.infer<typeof dashboardSpecSchema>["layout"]>;

export type StatPanel = z.infer<typeof statPanelSchema>;
export type TimeSeriesPanel = z.infer<typeof timeSeriesPanelSchema>;
export type HistogramPanel = z.infer<typeof histogramPanelSchema>;
export type TablePanel = z.infer<typeof tablePanelSchema>;
export type Panel = z.infer<typeof panelSchema>;
export type DashboardSpec = z.infer<typeof dashboardSpecSchema>;
