"use client";

import { useEffect, useId } from "react";
import { Maximize2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { getWidget } from "@/components/assistant/widgets/registry";
import { useWidgetInstances } from "@/components/assistant/widgets/WidgetInstanceProvider";
import { useWorkspace, type WidgetId } from "@/components/workspace/WorkspaceProvider";

type WidgetProps<TData> = {
  /** Registry key of the widget definition to render. */
  type: string;
  /** Result payload passed to the widget's renderers. */
  data: TData;
  /**
   * Stable instance id. Promotable widgets should pass a durable id (e.g. the
   * assistant-ui `toolCallId`) so a promoted widget survives a thread reload or
   * remount. Omitting it falls back to React's `useId`, which is stable only
   * for the lifetime of this mounted part — fine for inline-only widgets.
   */
  id?: WidgetId;
};

/**
 * Inline host for a registered widget. Resolves the definition by `type`,
 * registers the live instance so the Insights workspace can re-render it after
 * promotion, draws the compact `Inline` view, and — when an `Expanded` view
 * exists — overlays an "Open" affordance that promotes the widget into the
 * workspace (#30). Unknown types degrade to a visible fallback chip rather than
 * vanishing.
 */
export function Widget<TData>({ type, data, id }: WidgetProps<TData>) {
  const generatedId = useId();
  const widgetId = id ?? generatedId;

  const definition = getWidget(type);
  const { registerInstance } = useWidgetInstances();
  const { promoteWidget } = useWorkspace();

  // Only promotable widgets (those with an expanded view) need a stored
  // instance — the workspace re-renders them from their id alone. Inline-only
  // widgets are never promoted, so registering them would just retain their
  // data (and any callbacks) for nothing.
  const promotable = Boolean(definition?.Expanded);
  useEffect(() => {
    if (promotable) registerInstance({ id: widgetId, type, data });
  }, [promotable, registerInstance, widgetId, type, data]);

  if (!definition) {
    return (
      <div className="my-2 inline-flex items-center gap-2 rounded-md border border-dashed border-destructive/50 px-3 py-1.5 text-xs text-muted-foreground">
        Unknown widget: <span className="font-mono text-foreground">{type}</span>
      </div>
    );
  }

  const { Inline, Expanded } = definition;

  return (
    <div className="group relative">
      <Inline id={widgetId} data={data as never} />
      {Expanded ? (
        <Button
          variant="ghost"
          size="icon"
          onClick={() => promoteWidget(widgetId)}
          aria-label="Open in workspace"
          className="absolute right-2 top-2 h-7 w-7 opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
        >
          <Maximize2 className="h-3.5 w-3.5" />
        </Button>
      ) : null}
    </div>
  );
}
