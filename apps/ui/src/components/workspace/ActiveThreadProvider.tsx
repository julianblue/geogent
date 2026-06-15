"use client";

import { createContext, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";

/**
 * Tracks which LangGraph thread is currently active so the snapshot layer
 * (#20) knows where to read/write a conversation's map + insights state.
 *
 * It lives *above* RuntimeProvider (which sets the id from its `load`/stream
 * callbacks) and is read by <ThreadSnapshotSync>, which sits inside the
 * Workspace/MapState providers. Plain React context, matching the other
 * providers (no Zustand/Redux).
 */
type ActiveThreadContextValue = {
  activeThreadId: string | null;
  setActiveThreadId: (id: string | null) => void;
};

const ActiveThreadContext = createContext<ActiveThreadContextValue | null>(null);

export function ActiveThreadProvider({ children }: { children: ReactNode }) {
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const value = useMemo(() => ({ activeThreadId, setActiveThreadId }), [activeThreadId]);
  return <ActiveThreadContext.Provider value={value}>{children}</ActiveThreadContext.Provider>;
}

export function useActiveThread(): ActiveThreadContextValue {
  const ctx = useContext(ActiveThreadContext);
  if (!ctx) {
    throw new Error("useActiveThread must be used inside <ActiveThreadProvider>");
  }
  return ctx;
}
