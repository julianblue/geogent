"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";

export type WidgetId = string;

type WorkspaceContextValue = {
  openWidgetIds: WidgetId[];
  pinnedWidgetIds: WidgetId[];
  activeWidgetId: WidgetId | null;
  promoteWidget: (id: WidgetId) => void;
  closeWidget: (id: WidgetId) => void;
  setActiveWidget: (id: WidgetId | null) => void;
  pinWidget: (id: WidgetId) => void;
  unpinWidget: (id: WidgetId) => void;
  isOpen: (id: WidgetId) => boolean;
  isPinned: (id: WidgetId) => boolean;
};

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [openWidgetIds, setOpenWidgetIds] = useState<WidgetId[]>([]);
  const [pinnedWidgetIds, setPinnedWidgetIds] = useState<WidgetId[]>([]);
  const [activeWidgetId, setActiveWidgetId] = useState<WidgetId | null>(null);

  const promoteWidget = useCallback((id: WidgetId) => {
    setOpenWidgetIds((prev) => (prev.includes(id) ? prev : [...prev, id]));
    setActiveWidgetId(id);
  }, []);

  // Pinning is intentionally orthogonal to open state: a widget stays pinned
  // after being closed (pin = "keep around"), so closeWidget does not unpin.
  // The next active id is derived inside the open-list updater so batched
  // closes (e.g. "close all") each see the freshly-filtered list rather than a
  // stale snapshot.
  const closeWidget = useCallback((id: WidgetId) => {
    setOpenWidgetIds((prev) => {
      const remaining = prev.filter((wid) => wid !== id);
      setActiveWidgetId((active) =>
        active === id ? (remaining[remaining.length - 1] ?? null) : active,
      );
      return remaining;
    });
  }, []);

  const setActiveWidget = useCallback((id: WidgetId | null) => {
    if (id !== null) {
      setOpenWidgetIds((prev) => (prev.includes(id) ? prev : [...prev, id]));
    }
    setActiveWidgetId(id);
  }, []);

  const pinWidget = useCallback((id: WidgetId) => {
    setPinnedWidgetIds((prev) => (prev.includes(id) ? prev : [...prev, id]));
  }, []);

  const unpinWidget = useCallback((id: WidgetId) => {
    setPinnedWidgetIds((prev) => prev.filter((wid) => wid !== id));
  }, []);

  const isOpen = useCallback((id: WidgetId) => openWidgetIds.includes(id), [openWidgetIds]);
  const isPinned = useCallback((id: WidgetId) => pinnedWidgetIds.includes(id), [pinnedWidgetIds]);

  const value = useMemo<WorkspaceContextValue>(
    () => ({
      openWidgetIds,
      pinnedWidgetIds,
      activeWidgetId,
      promoteWidget,
      closeWidget,
      setActiveWidget,
      pinWidget,
      unpinWidget,
      isOpen,
      isPinned,
    }),
    [
      openWidgetIds,
      pinnedWidgetIds,
      activeWidgetId,
      promoteWidget,
      closeWidget,
      setActiveWidget,
      pinWidget,
      unpinWidget,
      isOpen,
      isPinned,
    ],
  );

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace(): WorkspaceContextValue {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) {
    throw new Error("useWorkspace must be used inside <WorkspaceProvider>");
  }
  return ctx;
}
