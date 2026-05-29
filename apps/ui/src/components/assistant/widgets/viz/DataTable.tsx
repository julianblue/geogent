"use client";

import type { ReactNode } from "react";

export type Column<T> = {
  key: string;
  header: ReactNode;
  /** Cell renderer; defaults to the row's value at `key`. */
  cell?: (row: T) => ReactNode;
  align?: "left" | "right";
  className?: string;
};

type DataTableProps<T> = {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T, index: number) => string;
  empty?: ReactNode;
};

/** Themed, dependency-free data table for the insights workspace. */
export function DataTable<T>({ columns, rows, rowKey, empty }: DataTableProps<T>) {
  if (rows.length === 0) {
    return <div className="text-sm text-muted-foreground">{empty ?? "No rows."}</div>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-muted-foreground">
            {columns.map((c) => (
              <th
                key={c.key}
                className={`py-2 font-medium ${c.align === "right" ? "text-right" : ""} ${c.className ?? ""}`}
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={rowKey(row, i)} className="border-b border-border/50">
              {columns.map((c) => (
                <td
                  key={c.key}
                  className={`py-2 ${c.align === "right" ? "text-right" : ""} ${c.className ?? ""}`}
                >
                  {c.cell ? c.cell(row) : (row as Record<string, ReactNode>)[c.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
