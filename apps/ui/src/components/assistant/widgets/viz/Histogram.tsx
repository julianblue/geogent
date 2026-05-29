"use client";

import {
  Bar,
  BarChart as RechartsBarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { axisProps, GRID_COLOR, seriesColor, tooltipStyle } from "./chartTheme";

export type HistogramBin = { label: string; count: number };

type HistogramProps = {
  bins: HistogramBin[];
  height?: number;
};

/**
 * Themed histogram — a gapless bar chart over pre-binned data (e.g. the
 * distribution of an index within a field polygon for zonal stats, #24).
 */
export function Histogram({ bins, height = 240 }: HistogramProps) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <RechartsBarChart data={bins} margin={{ top: 8, right: 12, bottom: 4, left: -8 }} barCategoryGap={1}>
        <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="label" {...axisProps} interval="preserveStartEnd" />
        <YAxis {...axisProps} />
        <Tooltip {...tooltipStyle} />
        <Bar dataKey="count" fill={seriesColor(1)} isAnimationActive={false} />
      </RechartsBarChart>
    </ResponsiveContainer>
  );
}
