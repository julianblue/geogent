"use client";

import {
  DataTable,
  Histogram,
  StatTile,
  StatTileGrid,
  TimeSeriesChart,
  type Column,
} from "@/components/assistant/widgets/viz";
import type { Panel, TablePanel, TimeSeriesPanel } from "./schema";

type TableRow = Record<string, string | number>;

function TimeSeriesPanelView({ panel }: { panel: TimeSeriesPanel }) {
  // The agent supplies each series independently; merge them into chart rows
  // keyed by x so multiple series share one axis.
  const rowsByX = new Map<string, TableRow>();
  for (const s of panel.series) {
    for (const p of s.points) {
      const row = rowsByX.get(p.x) ?? { x: p.x };
      row[s.key] = p.y;
      rowsByX.set(p.x, row);
    }
  }
  const rows = [...rowsByX.values()].sort((a, b) => String(a.x).localeCompare(String(b.x)));
  const series = panel.series.map((s) => ({ key: s.key, label: s.label }));
  return <TimeSeriesChart data={rows} xKey="x" series={series} />;
}

function TablePanelView({ panel }: { panel: TablePanel }) {
  const columns: Column<TableRow>[] = panel.columns.map((c) => ({
    key: c.key,
    header: c.header,
    align: c.align,
  }));
  return <DataTable columns={columns} rows={panel.rows} rowKey={(_row, i) => String(i)} />;
}

/**
 * Render one validated panel through the shared viz primitives. The exhaustive
 * switch means adding a panel type to the schema's discriminated union forces a
 * matching case here at compile time.
 */
export function PanelView({ panel }: { panel: Panel }) {
  switch (panel.type) {
    case "stat":
      return (
        <StatTileGrid>
          {panel.stats.map((s, i) => (
            <StatTile key={i} label={s.label} value={s.value} unit={s.unit} hint={s.hint} />
          ))}
        </StatTileGrid>
      );
    case "timeseries":
      return <TimeSeriesPanelView panel={panel} />;
    case "histogram":
      return <Histogram bins={panel.bins} />;
    case "table":
      return <TablePanelView panel={panel} />;
  }
}
