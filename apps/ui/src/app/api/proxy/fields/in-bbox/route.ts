import { NextRequest } from "next/server";

import { proxyJson } from "@/lib/api";

export async function GET(req: NextRequest) {
  // Forward the bbox query string through to the backend spatial filter.
  const search = req.nextUrl.search;
  return proxyJson(req, `/api/v1/fields/in-bbox${search}`);
}
