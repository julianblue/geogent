"use client";

import { useState } from "react";
import { CopilotChat } from "@copilotkit/react-ui";
import { Bot, MessageSquare, PanelRightClose, PanelRightOpen } from "lucide-react";

import { Button } from "@/components/ui/button";

const INSTRUCTIONS = `You are geogent, an agentic geospatial analyst.

Tools:
- flyTo(longitude, latitude, zoom?) — recenter the map after geocoding a place
- addBufferLayer(distanceMeters, geometryWkt?) — buffer a geometry; if no WKT is provided, the current viewport bbox is used
- listFeaturesInViewport() — list features stored in the DB that intersect the current view
- confirmFeatureSave(name, geometryWkt) — ask the user to confirm before persisting a feature

Always use map state from useCopilotReadable (viewport, features, selectedIds, layers) when relevant. Prefer the human-in-the-loop confirmation action whenever you are about to write to the database.`;

export function CopilotPanel() {
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
          Copilot
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setOpen((v) => !v)}
          aria-label={open ? "Collapse copilot" : "Open copilot"}
          className="ml-auto"
        >
          {open ? <PanelRightClose className="h-4 w-4" /> : <PanelRightOpen className="h-4 w-4" />}
        </Button>
      </div>

      {open ? (
        <div className="min-h-0 flex-1 overflow-hidden">
          <CopilotChat
            instructions={INSTRUCTIONS}
            labels={{
              title: "geogent",
              initial:
                "Hi! Ask me to fly to a place, buffer the visible area, or list features in view. I'll always confirm before writing to the database.",
              placeholder: "Ask geogent…",
            }}
            className="h-full"
          />
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-label="Open copilot"
          className="flex flex-1 items-center justify-center text-muted-foreground hover:text-foreground"
        >
          <MessageSquare className="h-4 w-4" />
        </button>
      )}
    </aside>
  );
}
