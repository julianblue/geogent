"use client";

import { PanelRightClose, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { getWidget } from "@/components/assistant/widgets/registry";
import { useWidgetInstances } from "@/components/assistant/widgets/WidgetInstanceProvider";
import { useWorkspace } from "@/components/workspace/WorkspaceProvider";

/**
 * Insights workspace surface (#17): the "expandable drawer" half of the
 * drawer+rail layout. When one or more widgets are promoted it expands to fill
 * the map area (the chat panel collapses to a rail — see AssistantPanel),
 * tabs across open widgets, and renders the active widget's `Expanded` view.
 * Closing the last widget removes the surface and restores the split layout.
 */
export function InsightsWorkspace() {
  const { openWidgetIds, activeWidgetId, setActiveWidget, closeWidget } = useWorkspace();
  const { getInstance } = useWidgetInstances();

  if (openWidgetIds.length === 0) return null;

  const activeId = activeWidgetId ?? openWidgetIds[openWidgetIds.length - 1];
  const activeInstance = getInstance(activeId);
  const activeDefinition = activeInstance ? getWidget(activeInstance.type) : undefined;
  const Expanded = activeDefinition?.Expanded;

  function closeAll() {
    for (const wid of [...openWidgetIds]) closeWidget(wid);
  }

  return (
    <div className="absolute inset-0 z-20 flex flex-col bg-background/95 backdrop-blur-sm">
      {/* Tab rail — lets multiple promoted widgets stack/tab in the workspace. */}
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
                className={`flex shrink-0 items-center gap-1 rounded-md border px-2 py-1 text-sm transition-colors ${
                  isActive
                    ? "border-border bg-accent text-accent-foreground"
                    : "border-transparent text-muted-foreground hover:bg-accent/50"
                }`}
              >
                <button
                  type="button"
                  onClick={() => setActiveWidget(wid)}
                  className="max-w-[200px] truncate"
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
          onClick={closeAll}
          aria-label="Close insights workspace"
          className="h-8 w-8 shrink-0"
          title="Close insights"
        >
          <PanelRightClose className="h-4 w-4" />
        </Button>
      </div>

      <div className="min-h-0 flex-1 overflow-auto p-6">
        <div className="mx-auto max-w-4xl">
          {activeInstance && Expanded ? (
            <Expanded id={activeInstance.id} data={activeInstance.data as never} />
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
              This widget has no expanded view.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
