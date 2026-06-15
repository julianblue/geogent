import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

// Mock the session resolver so we can drive authenticated/unauthenticated cases
// without touching the `server-only` auth module or the backend.
const getSession = vi.fn();
vi.mock("@/lib/auth", () => ({ getSession: () => getSession() }));

import { GET, POST } from "./route";

let fetchMock: ReturnType<typeof vi.fn>;

function req(path: string, init?: { method?: string; body?: string }): NextRequest {
  const method = init?.method ?? "GET";
  return new NextRequest(`http://localhost${path}`, {
    method,
    ...(init?.body !== undefined
      ? { body: init.body, headers: { "content-type": "application/json" } }
      : {}),
  });
}

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), { status });
}

beforeEach(() => {
  getSession.mockReset();
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("/api/lg proxy authorization", () => {
  it("returns 401 and forwards nothing when there is no session", async () => {
    getSession.mockResolvedValue(null);

    const res = await POST(req("/api/lg/threads/search", { method: "POST", body: "{}" }));

    expect(res.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("stamps the session owner onto thread creation", async () => {
    getSession.mockResolvedValue({ user: { id: 42 } });
    fetchMock.mockResolvedValueOnce(jsonResponse({ thread_id: "new" }));

    const res = await POST(
      req("/api/lg/threads", {
        method: "POST",
        body: JSON.stringify({ metadata: { title: "Hi" } }),
      }),
    );

    expect(res.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(init.body as string)).toEqual({ metadata: { title: "Hi", owner: "42" } });
  });

  it("forces the owner filter on search, overriding a client-supplied owner", async () => {
    getSession.mockResolvedValue({ user: { id: 42 } });
    fetchMock.mockResolvedValueOnce(jsonResponse([]));

    await POST(
      req("/api/lg/threads/search", {
        method: "POST",
        body: JSON.stringify({ metadata: { owner: "999" }, limit: 100 }),
      }),
    );

    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(init.body as string)).toEqual({ metadata: { owner: "42" }, limit: 100 });
  });

  it("forwards a thread-scoped request when the session user owns the thread", async () => {
    getSession.mockResolvedValue({ user: { id: 7 } });
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ metadata: { owner: "7" } })) // ownership check
      .mockResolvedValueOnce(new Response("ok", { status: 200 })); // forward

    const res = await GET(req("/api/lg/threads/t1/state"));

    expect(res.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[1][0]).toContain("/threads/t1/state");
  });

  it("returns 404 without forwarding when the thread belongs to another user", async () => {
    getSession.mockResolvedValue({ user: { id: 7 } });
    fetchMock.mockResolvedValueOnce(jsonResponse({ metadata: { owner: "other" } }));

    const res = await GET(req("/api/lg/threads/t1"));

    expect(res.status).toBe(404);
    expect(fetchMock).toHaveBeenCalledTimes(1); // ownership check only, no forward
  });

  it("returns 404 when the thread does not exist upstream", async () => {
    getSession.mockResolvedValue({ user: { id: 7 } });
    fetchMock.mockResolvedValueOnce(new Response("", { status: 404 }));

    const res = await GET(req("/api/lg/threads/missing"));

    expect(res.status).toBe(404);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("fails closed with 404 when the ownership check itself errors", async () => {
    getSession.mockResolvedValue({ user: { id: 7 } });
    fetchMock.mockRejectedValueOnce(new Error("network down"));

    const res = await GET(req("/api/lg/threads/t1/runs"));

    expect(res.status).toBe(404);
    expect(fetchMock).toHaveBeenCalledTimes(1); // ownership check only, no forward
  });

  it("passes through non-thread routes for authenticated users", async () => {
    getSession.mockResolvedValue({ user: { id: 1 } });
    fetchMock.mockResolvedValueOnce(new Response("ok", { status: 200 }));

    const res = await POST(req("/api/lg/assistants/search", { method: "POST", body: "{}" }));

    expect(res.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toContain("/assistants/search");
  });
});
