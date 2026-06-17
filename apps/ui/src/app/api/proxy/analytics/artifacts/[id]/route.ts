import { NextRequest } from "next/server";

import { proxyJson } from "@/lib/api";

// Artifact metadata (status + summary + assets). The UI uses this to resolve a
// reducer output's asset URL + colormap before rendering it; the heavy COG
// bytes are served by the sibling assets/[key] route.
export async function GET(_req: NextRequest, { params }: { params: { id: string } }) {
  return proxyJson(_req, `/api/v1/analytics/artifacts/${encodeURIComponent(params.id)}`);
}
