import { NextRequest } from "next/server";

import { proxyJson } from "@/lib/api";

export async function GET(req: NextRequest) {
  return proxyJson(req, `/api/v1/geocode/reverse${req.nextUrl.search}`);
}
