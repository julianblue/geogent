import { NextRequest } from "next/server";

import { backendFetch } from "@/lib/api";

// Cube-reduction assets are single-band COGs (one per reducer output:
// productivity.tif, stability.tif, slope.tif, frequency.tif, composite.tif, …).
// proxyJson can't carry them (it stringifies the body), so this route streams
// the raw bytes through with the session JWT attached for deck.gl-geotiff. The
// key is constrained to a simple `<name>.tif` to avoid path games; the backend
// also validates it against the artifact's declared assets.
const ASSET_KEY = /^[a-z][a-z0-9_]*\.tif$/;

export async function GET(_req: NextRequest, { params }: { params: { id: string; key: string } }) {
  const { id, key } = params;
  if (!ASSET_KEY.test(key)) {
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
