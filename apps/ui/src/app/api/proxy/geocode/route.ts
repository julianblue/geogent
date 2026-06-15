import { NextRequest } from "next/server";

import { proxyJson } from "@/lib/api";

export async function GET(req: NextRequest) {
  // Forward the ?q= (and optional ?limit=) query through to the geocoder.
  return proxyJson(req, `/api/v1/geocode${req.nextUrl.search}`);
}
