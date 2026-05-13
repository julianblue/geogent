import { NextResponse, type NextRequest } from "next/server";

const LANGGRAPH_URL = process.env.LANGGRAPH_URL ?? "http://localhost:2024";

async function handle(req: NextRequest, method: string) {
  try {
    const path = req.nextUrl.pathname.replace(/^\/?api\/lg\/?/, "");
    const search = new URLSearchParams(req.nextUrl.search);
    search.delete("_path");
    search.delete("nxtP_path");
    const qs = search.toString() ? `?${search.toString()}` : "";

    const init: RequestInit = {
      method,
      headers: {
        ...(process.env.LANGCHAIN_API_KEY ? { "x-api-key": process.env.LANGCHAIN_API_KEY } : {}),
        ...(req.headers.get("content-type")
          ? { "content-type": req.headers.get("content-type") as string }
          : {}),
      },
    };
    if (["POST", "PUT", "PATCH"].includes(method)) {
      init.body = await req.text();
    }

    const upstream = await fetch(`${LANGGRAPH_URL}/${path}${qs}`, init);
    const headers = new Headers(upstream.headers);
    headers.delete("content-encoding");
    headers.delete("content-length");
    headers.delete("transfer-encoding");
    return new NextResponse(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "proxy error";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}

export const GET = (req: NextRequest) => handle(req, "GET");
export const POST = (req: NextRequest) => handle(req, "POST");
export const PUT = (req: NextRequest) => handle(req, "PUT");
export const PATCH = (req: NextRequest) => handle(req, "PATCH");
export const DELETE = (req: NextRequest) => handle(req, "DELETE");
export const OPTIONS = () => new NextResponse(null, { status: 204 });
