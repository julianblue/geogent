import {
  CopilotRuntime,
  copilotRuntimeNextJSAppRouterEndpoint,
  langGraphPlatformEndpoint,
} from "@copilotkit/runtime";
import { NextRequest } from "next/server";

const LANGGRAPH_URL = process.env.LANGGRAPH_URL ?? "http://localhost:2024";
const GRAPH_ID = process.env.LANGGRAPH_GRAPH_ID ?? "geogent";

const runtime = new CopilotRuntime({
  remoteEndpoints: [
    langGraphPlatformEndpoint({
      deploymentUrl: LANGGRAPH_URL,
      agents: [{ name: GRAPH_ID, description: "Geogent geospatial analyst" }],
    }),
  ],
});

export const POST = async (req: NextRequest) => {
  const { handleRequest } = copilotRuntimeNextJSAppRouterEndpoint({
    runtime,
    serviceAdapter: undefined,
    endpoint: "/api/copilotkit",
  });
  return handleRequest(req);
};
