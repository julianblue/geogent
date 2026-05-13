"use client";

import { MapStateProvider } from "@/components/map/MapStateProvider";
import { MapView } from "@/components/map/MapView";
import { CopilotPanel } from "@/components/workspace/CopilotPanel";
import { useGeogentCopilot } from "@/components/copilot/actions";

function WorkspaceInner() {
  // Registers readables, actions, and suggestions. Must be inside MapStateProvider.
  useGeogentCopilot();
  return (
    <div className="flex h-full w-full min-h-0">
      <div className="relative flex-1">
        <MapView />
      </div>
      <CopilotPanel />
    </div>
  );
}

export function MapWorkspace() {
  return (
    <MapStateProvider>
      <WorkspaceInner />
    </MapStateProvider>
  );
}
