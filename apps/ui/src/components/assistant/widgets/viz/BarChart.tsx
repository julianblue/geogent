"use client";

import {
  Bar,
  BarChart as RechartsBarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { axisProps, GRID_COLOR, seriesColor, tooltipStyle } from "./chartTheme";

type ChartRow = Record<string, string | number>;

type BarChartProps = {
  data: ReadonlyArray<ChartRow>;
  /** Category axis key. */
  xKey: string;
  /** Value axis key. */
  yKey: string;
  height?: number;
  /** Color every bar the same (default) or cycle the palette per bar. */
  multicolor?: boolean;
};

/** Themed categorical bar chart (e.g. % change by class). */
export function BarChart({ data, xKey, yKey, height = 240, multicolor = false }: BarChartProps) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <RechartsBarChart
        data={data as ChartRow[]}
        margin={{ top: 8, right: 12, bottom: 4, left: -8 }}
      >
        <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey={xKey} {...axisProps} />
        <YAxis {...axisProps} />
        <Tooltip {...tooltipStyle} />
        <Bar dataKey={yKey} radius={[3, 3, 0, 0]} isAnimationActive={false} fill={seriesColor(0)}>
          {multicolor ? data.map((_, i) => <Cell key={i} fill={seriesColor(i)} />) : null}
        </Bar>
      </RechartsBarChart>
    </ResponsiveContainer>
  );
}
