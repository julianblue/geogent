"use client";

import { Sprout, X } from "lucide-react";

import { useMapState } from "@/components/map/MapStateProvider";

/**
 * Field-as-context (#24): when the user clicks a field on the map, surface it as
 * a removable chip above the composer so it's explicit which parcel the agent
 * will analyse. Drives `map_state.selected_field` (see RuntimeProvider). Renders
 * nothing when no field is selected.
 */
export function FieldContextChip() {
  const { fields, selectedFieldId, selectField } = useMapState();
  if (selectedFieldId == null) return null;

  const field = fields.find((f) => f.id === selectedFieldId);
  const label = field?.name ?? `Field ${selectedFieldId}`;

  return (
    <div className="flex flex-wrap items-center gap-1.5 px-1 pb-1">
      <span className="flex items-center gap-1 text-xs text-muted-foreground">
        <Sprout className="h-3.5 w-3.5" />
        Analysing field:
      </span>
      <span className="inline-flex items-center gap-1 rounded-full bg-accent px-2 py-0.5 text-xs text-accent-foreground">
        <span className="max-w-[160px] truncate">{label}</span>
        {field?.crop ? <span className="text-muted-foreground">· {field.crop}</span> : null}
        <button
          type="button"
          onClick={() => selectField(null)}
          aria-label={`Remove ${label} from context`}
          className="text-muted-foreground hover:text-foreground"
        >
          <X className="h-3 w-3" />
        </button>
      </span>
    </div>
  );
}
