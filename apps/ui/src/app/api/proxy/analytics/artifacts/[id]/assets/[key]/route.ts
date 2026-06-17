import { NextRequest } from "next/server";

import { backendFetch } from "@/lib/api";

// Field-memory assets are single-band COGs. proxyJson can't carry them (it
// stringifies the body), so this route streams the raw bytes through with the
// session JWT attached, for deck.gl-geotiff to fetch same-origin.
const ALLOWED_KEYS = new Set(["productivity.tif", "stability.tif"]);

export async function GET(_req: NextRequest, { params }: { params: { id: string; key: string } }) {
  const { id, key } = params;
  if (!ALLOWED_KEYS.has(key)) {
    return new Response("Not found", { status: 404 });
  }
  const path = `/api/v1/analytics/artifacts/${encodeURIComponent(id)}/assets/${encodeURIComponent(key)}`;
  const res = await backendFetch(path, { method: "GET" });
  if (!res.ok) {
    return new Response(null, { status: res.status });
  }
  return new Response(res.body, {
    status: res.status,
    headers: {
      "Content-Type": res.headers.get("Content-Type") ?? "image/tiff",
      "Cache-Control": "private, max-age=300",
    },
  });
}
