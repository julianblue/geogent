import { NextResponse, type NextRequest } from "next/server";
import { getSession } from "@/lib/auth";

const LANGGRAPH_URL = process.env.LANGGRAPH_URL ?? "http://localhost:2024";
const OWNER_KEY = "owner";

function apiKeyHeader(): Record<string, string> {
  return process.env.LANGCHAIN_API_KEY ? { "x-api-key": process.env.LANGCHAIN_API_KEY } : {};
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseObject(text: string | undefined): Record<string, unknown> {
  if (!text) return {};
  try {
    const parsed: unknown = JSON.parse(text);
    return isObject(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

/**
 * Force `metadata.owner` to the session user, preserving any other body fields
 * (e.g. `limit`/`sortBy` on search, `title` on create). Used both to stamp the
 * owner on thread creation and to constrain `/threads/search` so a caller can
 * only ever query their own threads — the client can't widen this.
 */
function withOwner(bodyText: string | undefined, userId: string): string {
  const body = parseObject(bodyText);
  const metadata = isObject(body.metadata) ? body.metadata : {};
  body.metadata = { ...metadata, [OWNER_KEY]: userId };
  return JSON.stringify(body);
}

/**
 * Verify the session user owns the thread before the proxy forwards a
 * thread-scoped request. Threads are stamped with an `owner` metadata tag on
 * creation; a missing or mismatched owner (or any upstream read failure) is
 * treated as not-owned — fail closed.
 */
async function ownsThread(threadId: string, userId: string): Promise<boolean> {
  const res = await fetch(`${LANGGRAPH_URL}/threads/${encodeURIComponent(threadId)}`, {
    method: "GET",
    headers: apiKeyHeader(),
  });
  if (!res.ok) return false;
  const thread = (await res.json()) as { metadata?: Record<string, unknown> };
  return thread.metadata?.[OWNER_KEY] === userId;
}

async function handle(req: NextRequest, method: string) {
  try {
    // The proxy is the authorization boundary: every LangGraph call must be made
    // by an authenticated user, and thread access is scoped to its owner. The
    // client-side owner check in threadListAdapter is now defense-in-depth.
    const session = await getSession();
    if (!session) {
      return NextResponse.json({ error: "unauthorized" }, { status: 401 });
    }
    const userId = String(session.user.id);

    const path = req.nextUrl.pathname.replace(/^\/?api\/lg\/?/, "");
    const search = new URLSearchParams(req.nextUrl.search);
    search.delete("_path");
    search.delete("nxtP_path");
    const qs = search.toString() ? `?${search.toString()}` : "";

    const segments = path.split("/").filter(Boolean);

    let bodyText: string | undefined;
    if (["POST", "PUT", "PATCH"].includes(method)) {
      bodyText = await req.text();
    }

    // Per-user authorization for thread-scoped routes. `/threads` (create) and
    // `/threads/search` (list) are owner-stamped server-side; `/threads/{id}...`
    // is gated on ownership and returns 404 to avoid leaking thread existence.
    if (segments[0] === "threads") {
      const second = segments[1];
      if (second === undefined) {
        if (method === "POST") bodyText = withOwner(bodyText, userId);
      } else if (second === "search") {
        if (method === "POST") bodyText = withOwner(bodyText, userId);
      } else if (!(await ownsThread(second, userId))) {
        return NextResponse.json({ error: "not found" }, { status: 404 });
      }
    }

    const init: RequestInit = {
      method,
      headers: {
        ...apiKeyHeader(),
        ...(req.headers.get("content-type")
          ? { "content-type": req.headers.get("content-type") as string }
          : {}),
      },
    };
    if (bodyText !== undefined) {
      init.body = bodyText;
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
