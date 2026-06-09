"use client";

import { useState } from "react";
import { Bot, MessageSquare, PanelRightClose, PanelRightOpen } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Thread } from "@/components/assistant/Thread";
import { FlyToTool } from "@/components/assistant/tools/FlyToTool";
import { BufferLayerTool } from "@/components/assistant/tools/BufferLayerTool";
import { FeaturesInViewportTool } from "@/components/assistant/tools/FeaturesInViewportTool";
import { ConfirmFeatureSaveTool } from "@/components/assistant/tools/ConfirmFeatureSaveTool";
import { RenderDashboardTool } from "@/components/assistant/tools/RenderDashboardTool";
import { ZonalStatsTool } from "@/components/assistant/tools/agriculture/ZonalStatsTool";
import { IndexTimeSeriesTool } from "@/components/assistant/tools/agriculture/IndexTimeSeriesTool";
import { Sentinel2SceneWidgetTool } from "@/components/assistant/tools/agriculture/Sentinel2SceneWidgetTool";
import { useWorkspace } from "@/components/workspace/WorkspaceProvider";

export function AssistantPanel() {
  const [userOpen, setUserOpen] = useState(true);
  // The drawer+rail layout (#17): while a widget is promoted into the insights
  // workspace, the chat collapses to a rail to give the expanded surface room.
  // Closing the widget restores the user's prior open/collapsed preference.
  const { openWidgetIds } = useWorkspace();
  const insightsOpen = openWidgetIds.length > 0;
  const expanded = userOpen && !insightsOpen;

  return (
    <aside
      className={`flex h-full shrink-0 flex-col border-l border-border bg-card transition-[width] duration-200 ease-in-out ${
        expanded ? "w-[420px]" : "w-12"
      }`}
    >
      <div className="flex h-12 shrink-0 items-center justify-between border-b border-border px-3">
        <div className={`flex items-center gap-2 text-sm font-medium ${expanded ? "" : "hidden"}`}>
          <Bot className="h-4 w-4 text-primary" />
          geogent
        </div>
        {!insightsOpen ? (
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setUserOpen((v) => !v)}
            aria-label={userOpen ? "Collapse assistant" : "Open assistant"}
            className="ml-auto"
          >
            {userOpen ? (
              <PanelRightClose className="h-4 w-4" />
            ) : (
              <PanelRightOpen className="h-4 w-4" />
            )}
          </Button>
        ) : null}
      </div>

      <FlyToTool />
      <BufferLayerTool />
      <FeaturesInViewportTool />
      <ConfirmFeatureSaveTool />
      <RenderDashboardTool />
      <ZonalStatsTool />
      <IndexTimeSeriesTool />
      <Sentinel2SceneWidgetTool />

      {expanded ? (
        <div className="min-h-0 flex-1 overflow-hidden">
          <Thread />
        </div>
      ) : (
        <div
          className="flex flex-1 items-center justify-center text-muted-foreground"
          aria-hidden={insightsOpen}
        >
          {insightsOpen ? (
            <MessageSquare className="h-4 w-4" />
          ) : (
            <button
              type="button"
              onClick={() => setUserOpen(true)}
              aria-label="Open assistant"
              className="flex flex-1 items-center justify-center self-stretch hover:text-foreground"
            >
              <MessageSquare className="h-4 w-4" />
            </button>
          )}
        </div>
      )}
    </aside>
  );
}
