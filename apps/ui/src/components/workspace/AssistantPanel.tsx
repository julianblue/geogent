"use client";

import { useState } from "react";
import { Bot, MessageSquare, PanelRightClose, PanelRightOpen } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Thread } from "@/components/assistant/Thread";
import { FlyToTool } from "@/components/assistant/tools/FlyToTool";
import { BufferLayerTool } from "@/components/assistant/tools/BufferLayerTool";
import { FeaturesInViewportTool } from "@/components/assistant/tools/FeaturesInViewportTool";
import { ConfirmFeatureSaveTool } from "@/components/assistant/tools/ConfirmFeatureSaveTool";

export function AssistantPanel() {
  const [open, setOpen] = useState(true);

  return (
    <aside
      className={`flex h-full shrink-0 flex-col border-l border-border bg-card transition-[width] duration-200 ease-in-out ${
        open ? "w-[420px]" : "w-12"
      }`}
    >
      <div className="flex h-12 shrink-0 items-center justify-between border-b border-border px-3">
        <div className={`flex items-center gap-2 text-sm font-medium ${open ? "" : "hidden"}`}>
          <Bot className="h-4 w-4 text-primary" />
          geogent
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setOpen((v) => !v)}
          aria-label={open ? "Collapse assistant" : "Open assistant"}
          className="ml-auto"
        >
          {open ? (
            <PanelRightClose className="h-4 w-4" />
          ) : (
            <PanelRightOpen className="h-4 w-4" />
          )}
        </Button>
      </div>

      <FlyToTool />
      <BufferLayerTool />
      <FeaturesInViewportTool />
      <ConfirmFeatureSaveTool />

      {open ? (
        <div className="min-h-0 flex-1 overflow-hidden">
          <Thread />
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-label="Open assistant"
          className="flex flex-1 items-center justify-center text-muted-foreground hover:text-foreground"
        >
          <MessageSquare className="h-4 w-4" />
        </button>
      )}
    </aside>
  );
}
