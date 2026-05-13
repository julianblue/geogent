"use client";

import { MapStateProvider } from "@/components/map/MapStateProvider";
import { MapView } from "@/components/map/MapView";
import { RuntimeProvider } from "@/components/assistant/RuntimeProvider";
import { AssistantPanel } from "@/components/workspace/AssistantPanel";

export function MapWorkspace() {
  return (
    <MapStateProvider>
      <RuntimeProvider>
        <div className="flex h-full min-h-0 w-full">
          <div className="relative flex-1">
            <MapView />
          </div>
          <AssistantPanel />
        </div>
      </RuntimeProvider>
    </MapStateProvider>
  );
}
