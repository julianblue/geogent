"use client";

import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

import type { WidgetId } from "@/components/workspace/WorkspaceProvider";
import type { WidgetInstance } from "@/components/assistant/widgets/types";

/**
 * Holds the *data* behind promoted widgets, keyed by widget id.
 *
 * WorkspaceProvider (#30) deliberately tracks only ids (which widget is
 * open/active). But the Insights surface needs to re-render an expanded widget
 * from its id alone — long after the originating transcript message is gone —
 * so the `{ type, data }` payload needs a home. This small context is that
 * home, kept separate from WorkspaceProvider so #30 stays focused on
 * selection state. Plain React context, matching MapStateProvider /
 * WorkspaceProvider (no Zustand/Redux).
 */
type WidgetInstanceContextValue = {
  registerInstance: (instance: WidgetInstance) => void;
  getInstance: (id: WidgetId) => WidgetInstance | undefined;
};

const WidgetInstanceContext = createContext<WidgetInstanceContextValue | null>(null);

export function WidgetInstanceProvider({ children }: { children: ReactNode }) {
  // Instances live in a ref (the source of truth, written on every render of a
  // <Widget>) plus a version counter that bumps when a *new* id appears, so the
  // workspace re-renders when something is promoted. Updates to an existing id's
  // data don't need to force a re-render here — the inline widget already did.
  const instances = useRef<Map<WidgetId, WidgetInstance>>(new Map());
  const [, setVersion] = useState(0);

  const registerInstance = useCallback((instance: WidgetInstance) => {
    const existing = instances.current.get(instance.id);
    instances.current.set(instance.id, instance);
    if (!existing) setVersion((v) => v + 1);
  }, []);

  const getInstance = useCallback((id: WidgetId) => instances.current.get(id), []);

  const value = useMemo<WidgetInstanceContextValue>(
    () => ({ registerInstance, getInstance }),
    [registerInstance, getInstance],
  );

  return (
    <WidgetInstanceContext.Provider value={value}>{children}</WidgetInstanceContext.Provider>
  );
}

export function useWidgetInstances(): WidgetInstanceContextValue {
  const ctx = useContext(WidgetInstanceContext);
  if (!ctx) {
    throw new Error("useWidgetInstances must be used inside <WidgetInstanceProvider>");
  }
  return ctx;
}
