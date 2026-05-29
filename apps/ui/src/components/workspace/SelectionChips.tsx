"use client";

import { MapPin, X } from "lucide-react";

import { useMapState } from "@/components/map/MapStateProvider";

/**
 * Selection-as-context (#19): surfaces the features the user has clicked on the
 * map as removable chips above the composer, making explicit what gets shipped
 * to the agent as `map_state.selected_ids` (see RuntimeProvider). Renders
 * nothing when there is no selection.
 */
export function SelectionChips() {
  const { features, selectedIds, toggleSelected, clearSelected } = useMapState();
  if (selectedIds.length === 0) return null;

  const nameFor = (id: string) => features.find((f) => f.id === id)?.name ?? id;

  return (
    <div className="flex flex-wrap items-center gap-1.5 px-1 pb-1">
      <span className="flex items-center gap-1 text-xs text-muted-foreground">
        <MapPin className="h-3.5 w-3.5" />
        Ask about {selectedIds.length} feature{selectedIds.length === 1 ? "" : "s"}:
      </span>
      {selectedIds.map((id) => (
        <span
          key={id}
          className="inline-flex items-center gap-1 rounded-full bg-accent px-2 py-0.5 text-xs text-accent-foreground"
        >
          <span className="max-w-[140px] truncate">{nameFor(id)}</span>
          <button
            type="button"
            onClick={() => toggleSelected(id)}
            aria-label={`Remove ${nameFor(id)} from context`}
            className="text-muted-foreground hover:text-foreground"
          >
            <X className="h-3 w-3" />
          </button>
        </span>
      ))}
      <button
        type="button"
        onClick={clearSelected}
        className="text-xs text-muted-foreground underline-offset-2 hover:underline"
      >
        Clear
      </button>
    </div>
  );
}
