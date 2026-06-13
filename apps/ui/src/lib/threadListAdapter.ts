import type { Client, Thread } from "@langchain/langgraph-sdk";
import type { RemoteThreadListAdapter } from "@assistant-ui/react";
import { type AssistantStreamController, createAssistantStream } from "assistant-stream";

/**
 * Thread-list adapter backing the assistant-ui thread list with the LangGraph
 * SDK's `client.threads` API (#20). The LangGraph thread *is* the remote store,
 * so `remoteId` and `externalId` are both the LangGraph `thread_id` — there is
 * no separate assistant-cloud record. Threads are scoped per logged-in user via
 * an `owner` metadata tag so one user never sees another's conversations.
 *
 * `title`/`archived` live in thread metadata; LangGraph patches (merges)
 * metadata on update, so writing one key preserves the others.
 */

const OWNER_KEY = "owner";
const TITLE_KEY = "title";
const ARCHIVED_KEY = "archived";

function titleOf(thread: Thread): string | undefined {
  const value = thread.metadata?.[TITLE_KEY];
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function isArchived(thread: Thread): boolean {
  return thread.metadata?.[ARCHIVED_KEY] === true;
}

function toMetadata(thread: Thread) {
  return {
    status: isArchived(thread) ? ("archived" as const) : ("regular" as const),
    remoteId: thread.thread_id,
    externalId: thread.thread_id,
    title: titleOf(thread),
  };
}

export function createLangGraphThreadListAdapter(options: {
  client: Client;
  userId: string;
}): RemoteThreadListAdapter {
  const { client, userId } = options;
  const ownerScope = { [OWNER_KEY]: userId };

  return {
    async list() {
      const threads = await client.threads.search({
        metadata: ownerScope,
        limit: 100,
        sortBy: "updated_at",
        sortOrder: "desc",
      });
      return { threads: threads.map(toMetadata) };
    },

    async initialize() {
      const thread = await client.threads.create({ metadata: ownerScope });
      return { remoteId: thread.thread_id, externalId: thread.thread_id };
    },

    async rename(remoteId, newTitle) {
      await client.threads.update(remoteId, { metadata: { [TITLE_KEY]: newTitle } });
    },

    async archive(remoteId) {
      await client.threads.update(remoteId, { metadata: { [ARCHIVED_KEY]: true } });
    },

    async unarchive(remoteId) {
      await client.threads.update(remoteId, { metadata: { [ARCHIVED_KEY]: false } });
    },

    async delete(remoteId) {
      await client.threads.delete(remoteId);
    },

    async fetch(remoteId) {
      const thread = await client.threads.get(remoteId);
      return toMetadata(thread);
    },

    // Titles are derived client-side from the first user turn (see
    // RuntimeProvider); this method is not invoked by the current runtime build
    // but is required by the adapter contract, so it returns an empty stream.
    async generateTitle() {
      return createAssistantStream((controller: AssistantStreamController) => {
        controller.close();
      });
    },
  };
}
