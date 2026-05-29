"use client";

import type { ReactNode } from "react";

import { Card } from "@/components/ui/card";

type StatTileProps = {
  label: string;
  value: ReactNode;
  /** Optional unit/suffix rendered next to the value (e.g. "m", "%"). */
  unit?: string;
  /** Optional smaller line under the value (e.g. provenance, delta). */
  hint?: ReactNode;
};

/** Compact metric tile for the insights workspace, themed to the token system. */
export function StatTile({ label, value, unit, hint }: StatTileProps) {
  return (
    <Card className="p-3">
      <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="mt-1 flex items-baseline gap-1">
        <span className="text-2xl font-semibold tabular-nums">{value}</span>
        {unit ? <span className="text-sm text-muted-foreground">{unit}</span> : null}
      </div>
      {hint ? <div className="mt-1 text-xs text-muted-foreground">{hint}</div> : null}
    </Card>
  );
}

/** Responsive grid wrapper so tiles flow into columns. */
export function StatTileGrid({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">{children}</div>;
}
