"use client";

import { CopilotSidebar as CKSidebar } from "@copilotkit/react-ui";

export function CopilotSidebar() {
  return (
    <CKSidebar
      defaultOpen
      labels={{
        title: "geogent",
        initial:
          "Hi! I'm geogent. Ask me to explore places, buffer geometries, or list features on the map.",
      }}
      instructions="You are geogent, an agentic geospatial analyst. Use your tools to answer."
    />
  );
}
