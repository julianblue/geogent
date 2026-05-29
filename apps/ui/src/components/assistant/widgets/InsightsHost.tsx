"use client";

import { X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { getWidget } from "@/components/assistant/widgets/registry";
import { useWidgetInstances } from "@/components/assistant/widgets/WidgetInstanceProvider";
import { useWorkspace } from "@/components/workspace/WorkspaceProvider";

/**
 * Minimal Insights surface — a placeholder that proves widget promotion
 * end-to-end (#16). It overlays the map area, renders the active promoted
 * widget's `Expanded` view, offers a tab strip when several are open, and a
 * close button. Issue #17 replaces this with the real expandable drawer + rail;
 * keep it deliberately simple.
 */
export function InsightsHost() {
  const { openWidgetIds, activeWidgetId, setActiveWidget, closeWidget } = useWorkspace();
  const { getInstance } = useWidgetInstances();

  if (openWidgetIds.length === 0) return null;

  const activeId = activeWidgetId ?? openWidgetIds[openWidgetIds.length - 1];
  const activeInstance = getInstance(activeId);
  const activeDefinition = activeInstance ? getWidget(activeInstance.type) : undefined;
  const Expanded = activeDefinition?.Expanded;

  return (
    <div className="absolute inset-0 z-20 flex flex-col bg-background/95 backdrop-blur-sm">
      <div className="flex h-12 shrink-0 items-center gap-1 border-b border-border px-2">
        <div className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto">
          {openWidgetIds.map((wid) => {
            const inst = getInstance(wid);
            const def = inst ? getWidget(inst.type) : undefined;
            const label = inst && def?.title ? def.title(inst.data as never) : (inst?.type ?? wid);
            const isActive = wid === activeId;
            return (
              <div
                key={wid}
                className={`flex shrink-0 items-center gap-1 rounded-md px-2 py-1 text-sm ${
                  isActive ? "bg-accent text-accent-foreground" : "text-muted-foreground"
                }`}
              >
                <button
                  type="button"
                  onClick={() => setActiveWidget(wid)}
                  className="max-w-[180px] truncate hover:text-foreground"
                >
                  {label}
                </button>
                <button
                  type="button"
                  onClick={() => closeWidget(wid)}
                  aria-label="Close widget"
                  className="text-muted-foreground hover:text-foreground"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            );
          })}
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => closeWidget(activeId)}
          aria-label="Close insights"
          className="h-8 w-8 shrink-0"
        >
          <X className="h-4 w-4" />
        </Button>
      </div>

      <div className="min-h-0 flex-1 overflow-auto p-4">
        {activeInstance && Expanded ? (
          <Expanded id={activeInstance.id} data={activeInstance.data as never} />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            This widget has no expanded view.
          </div>
        )}
      </div>
    </div>
  );
}
