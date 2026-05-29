"use client";

import { MapStateProvider } from "@/components/map/MapStateProvider";
import { MapView } from "@/components/map/MapView";
import { Sentinel2Overlay } from "@/components/map/Sentinel2Overlay";
import { RuntimeProvider } from "@/components/assistant/RuntimeProvider";
import { Sentinel2RenderTool } from "@/components/assistant/tools/Sentinel2RenderTool";
import { AssistantPanel } from "@/components/workspace/AssistantPanel";
import { WorkspaceProvider } from "@/components/workspace/WorkspaceProvider";
import { WidgetInstanceProvider, InsightsHost } from "@/components/assistant/widgets";

export function MapWorkspace() {
  return (
    <MapStateProvider>
      <RuntimeProvider>
        {/* Interrupt handlers must live inside RuntimeProvider so they can
            subscribe to the LangGraph thread state, but outside the visible
            layout so they render nothing. */}
        <Sentinel2RenderTool />
        <WidgetInstanceProvider>
          <WorkspaceProvider>
            <div className="flex h-full min-h-0 w-full">
              <div className="relative flex-1">
                <MapView />
                <Sentinel2Overlay />
                {/* Minimal Insights surface (#16); #17 replaces with drawer+rail. */}
                <InsightsHost />
              </div>
              <AssistantPanel />
            </div>
          </WorkspaceProvider>
        </WidgetInstanceProvider>
      </RuntimeProvider>
    </MapStateProvider>
  );
}
