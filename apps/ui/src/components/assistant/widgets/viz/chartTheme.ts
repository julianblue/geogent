/**
 * Shared chart theming. Recharts needs concrete color strings, so we reference
 * the design-system CSS variables via `hsl(var(--token))` — which resolves to
 * the right value in light and dark automatically. Keep all chart color/axis
 * decisions here so every viz primitive stays consistent with the token system.
 */
export const CHART_COLORS = [
  "hsl(var(--chart-1))",
  "hsl(var(--chart-2))",
  "hsl(var(--chart-3))",
  "hsl(var(--chart-4))",
  "hsl(var(--chart-5))",
] as const;

/** Pick a series color by index, wrapping around the palette. */
export function seriesColor(index: number): string {
  return CHART_COLORS[index % CHART_COLORS.length];
}

export const AXIS_COLOR = "hsl(var(--muted-foreground))";
export const GRID_COLOR = "hsl(var(--border))";

/** Common axis props so every chart shares tick styling. */
export const axisProps = {
  stroke: AXIS_COLOR,
  fontSize: 11,
  tickLine: false,
  axisLine: { stroke: GRID_COLOR },
} as const;

/** Tooltip styling that matches popover surfaces in both themes. */
export const tooltipStyle = {
  contentStyle: {
    background: "hsl(var(--popover))",
    border: "1px solid hsl(var(--border))",
    borderRadius: "var(--radius)",
    color: "hsl(var(--popover-foreground))",
    fontSize: 12,
  },
  labelStyle: { color: "hsl(var(--muted-foreground))" },
  cursor: { fill: "hsl(var(--accent))", opacity: 0.3 },
} as const;
