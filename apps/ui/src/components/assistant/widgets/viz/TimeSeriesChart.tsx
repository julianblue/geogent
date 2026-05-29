"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { axisProps, GRID_COLOR, seriesColor, tooltipStyle } from "./chartTheme";

export type Series = { key: string; label?: string; color?: string };

type ChartRow = Record<string, string | number>;

type TimeSeriesChartProps = {
  data: ReadonlyArray<ChartRow>;
  xKey: string;
  series: Series[];
  height?: number;
  /** Optional formatter for the X axis tick (e.g. dates). */
  xTickFormatter?: (value: string | number) => string;
};

/** Themed multi-series line chart for time-series data (e.g. seasonal NDVI). */
export function TimeSeriesChart({
  data,
  xKey,
  series,
  height = 240,
  xTickFormatter,
}: TimeSeriesChartProps) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data as ChartRow[]} margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
        <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey={xKey} tickFormatter={xTickFormatter} {...axisProps} />
        <YAxis {...axisProps} />
        <Tooltip {...tooltipStyle} />
        {series.map((s, i) => (
          <Line
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.label ?? s.key}
            stroke={s.color ?? seriesColor(i)}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
            isAnimationActive={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
