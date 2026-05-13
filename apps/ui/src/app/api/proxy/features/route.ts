import { NextRequest } from "next/server";

import { proxyJson } from "@/lib/api";

export async function GET(req: NextRequest) {
  return proxyJson(req, "/api/v1/features");
}

export async function POST(req: NextRequest) {
  return proxyJson(req, "/api/v1/features");
}
