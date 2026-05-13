import "server-only";

import { getAuthToken } from "@/lib/auth";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function backendFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = getAuthToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return fetch(`${BACKEND_URL}${path}`, { ...init, headers, cache: "no-store" });
}

/** Forward the current request body to a backend path. Used by /api/proxy/* handlers. */
export async function proxyJson(req: Request, backendPath: string): Promise<Response> {
  const body = req.method === "GET" || req.method === "HEAD" ? undefined : await req.text();
  const res = await backendFetch(backendPath, {
    method: req.method,
    body,
  });
  const text = await res.text();
  return new Response(text, {
    status: res.status,
    headers: {
      "Content-Type": res.headers.get("Content-Type") ?? "application/json",
    },
  });
}
