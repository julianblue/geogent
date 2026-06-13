import { describe, expect, it, vi } from "vitest";
import type { Client, Thread } from "@langchain/langgraph-sdk";

import { createLangGraphThreadListAdapter } from "./threadListAdapter";

function fakeThread(overrides: Partial<Thread> = {}): Thread {
  return {
    thread_id: "t1",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    state_updated_at: "2026-01-01T00:00:00Z",
    metadata: {},
    status: "idle",
    values: {},
    interrupts: {},
    ...overrides,
  } as Thread;
}

function makeClient(threads: ReturnType<typeof vi.fn>, owner = "1") {
  const search = vi.fn(async () => threads());
  const create = vi.fn(async () => fakeThread({ thread_id: "new-thread" }));
  const update = vi.fn(async () => undefined);
  const del = vi.fn(async () => undefined);
  const get = vi.fn(async () => fakeThread({ thread_id: "t1", metadata: { owner } }));
  const client = { threads: { search, create, update, delete: del, get } } as unknown as Client;
  return { client, search, create, update, del, get };
}

describe("createLangGraphThreadListAdapter", () => {
  it("scopes list() to the owner and maps title/archived metadata", async () => {
    const { client, search } = makeClient(
      vi.fn(() => [
        fakeThread({ thread_id: "a", metadata: { owner: "7", title: "Crop health" } }),
        fakeThread({ thread_id: "b", metadata: { owner: "7", archived: true } }),
      ]),
    );
    const adapter = createLangGraphThreadListAdapter({ client, userId: "7" });

    const { threads } = await adapter.list();

    expect(search).toHaveBeenCalledWith(
      expect.objectContaining({ metadata: { owner: "7" }, sortBy: "updated_at" }),
    );
    expect(threads).toEqual([
      { status: "regular", remoteId: "a", externalId: "a", title: "Crop health" },
      { status: "archived", remoteId: "b", externalId: "b", title: undefined },
    ]);
  });

  it("creates owner-tagged threads where remoteId equals externalId", async () => {
    const { client, create } = makeClient(vi.fn(() => []));
    const adapter = createLangGraphThreadListAdapter({ client, userId: "42" });

    const result = await adapter.initialize("ignored-local-id");

    expect(create).toHaveBeenCalledWith({ metadata: { owner: "42" } });
    expect(result).toEqual({ remoteId: "new-thread", externalId: "new-thread" });
  });

  it("renames, archives, unarchives, and deletes via thread metadata", async () => {
    const { client, update, del } = makeClient(vi.fn(() => []));
    const adapter = createLangGraphThreadListAdapter({ client, userId: "1" });

    await adapter.rename("a", "Field A history");
    await adapter.archive("a");
    await adapter.unarchive("a");
    await adapter.delete("a");

    expect(update).toHaveBeenNthCalledWith(1, "a", { metadata: { title: "Field A history" } });
    expect(update).toHaveBeenNthCalledWith(2, "a", { metadata: { archived: true } });
    expect(update).toHaveBeenNthCalledWith(3, "a", { metadata: { archived: false } });
    expect(del).toHaveBeenCalledWith("a");
  });

  it("fails closed on mutate/fetch when the thread is owned by someone else", async () => {
    const { client, update, del } = makeClient(
      vi.fn(() => []),
      "other-user",
    );
    const adapter = createLangGraphThreadListAdapter({ client, userId: "1" });

    await expect(adapter.fetch("a")).rejects.toThrow(/not owned/);
    await expect(adapter.rename("a", "x")).rejects.toThrow(/not owned/);
    await expect(adapter.archive("a")).rejects.toThrow(/not owned/);
    await expect(adapter.delete("a")).rejects.toThrow(/not owned/);
    expect(update).not.toHaveBeenCalled();
    expect(del).not.toHaveBeenCalled();
  });

  it("fetch() returns mapped metadata for an owned thread", async () => {
    const { client, get } = makeClient(
      vi.fn(() => []),
      "1",
    );
    get.mockResolvedValueOnce(
      fakeThread({ thread_id: "a", metadata: { owner: "1", title: "Owned" } }),
    );
    const adapter = createLangGraphThreadListAdapter({ client, userId: "1" });

    await expect(adapter.fetch("a")).resolves.toEqual({
      status: "regular",
      remoteId: "a",
      externalId: "a",
      title: "Owned",
    });
  });

  it("treats blank/non-string titles as untitled", async () => {
    const { client } = makeClient(
      vi.fn(() => [fakeThread({ thread_id: "c", metadata: { owner: "1", title: "" } })]),
    );
    const adapter = createLangGraphThreadListAdapter({ client, userId: "1" });

    const { threads } = await adapter.list();
    expect(threads[0]?.title).toBeUndefined();
  });
});
