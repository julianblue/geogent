"use client";

import { MapStateProvider } from "@/components/map/MapStateProvider";
import { MapView } from "@/components/map/MapView";
import { Sentinel2Overlay } from "@/components/map/Sentinel2Overlay";
import { AggregationOverlay } from "@/components/map/AggregationOverlay";
import { LayerSync } from "@/components/map/LayerSync";
import { LayerManager } from "@/components/map/LayerManager";
import { RuntimeProvider } from "@/components/assistant/RuntimeProvider";
import { Sentinel2RenderTool } from "@/components/assistant/tools/Sentinel2RenderTool";
import { AssistantPanel } from "@/components/workspace/AssistantPanel";
import { ActiveThreadProvider } from "@/components/workspace/ActiveThreadProvider";
import { WorkspaceProvider } from "@/components/workspace/WorkspaceProvider";
import { ThreadSnapshotSync } from "@/components/workspace/ThreadSnapshotSync";
import { WidgetInstanceProvider, InsightsWorkspace } from "@/components/assistant/widgets";

export function MapWorkspace({ userId }: { userId: string }) {
  return (
    <MapStateProvider>
      {/* Tracks the active LangGraph thread so per-thread map/insights snapshots
          (#20) can be read/written. Wraps RuntimeProvider (which sets the id)
          and ThreadSnapshotSync (which reads it). */}
      <ActiveThreadProvider>
        <RuntimeProvider userId={userId}>
          {/* Interrupt handlers must live inside RuntimeProvider so they can
              subscribe to the LangGraph thread state, but outside the visible
              layout so they render nothing. */}
          <Sentinel2RenderTool />
          <WidgetInstanceProvider>
            <WorkspaceProvider>
              {/* Restores a conversation's map + insights on reopen and
                  persists changes back to thread metadata. Renders nothing. */}
              <ThreadSnapshotSync />
              <div className="flex h-full min-h-0 w-full">
                <div className="relative flex-1">
                  <MapView />
                  <Sentinel2Overlay />
                  <AggregationOverlay />
                  <LayerSync />
                  <LayerManager />
                  {/* Insights surface (#17): expands over the map when a widget
                      is promoted; the chat panel collapses to a rail. */}
                  <InsightsWorkspace />
                </div>
                <AssistantPanel />
              </div>
            </WorkspaceProvider>
          </WidgetInstanceProvider>
        </RuntimeProvider>
      </ActiveThreadProvider>
    </MapStateProvider>
  );
}
