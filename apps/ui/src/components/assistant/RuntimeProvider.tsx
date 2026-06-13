"use client";

import { useMemo, useRef } from "react";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { useLangGraphRuntime, type LangChainMessage } from "@assistant-ui/react-langgraph";

import { useMapState } from "@/components/map/MapStateProvider";
import {
  createClient,
  deriveThreadTitle,
  getCheckpointId,
  getThreadState,
  sendMessage,
  setInitialThreadTitle,
} from "@/lib/chatApi";
import { createLangGraphThreadListAdapter } from "@/lib/threadListAdapter";

export function RuntimeProvider({
  userId,
  children,
}: {
  userId: string;
  children: React.ReactNode;
}) {
  const { viewport, features, selectedIds, fields, selectedFieldId, layers } = useMapState();
  // Snapshot the latest map state into a ref so the async stream callback
  // always reads the freshest value without recreating the runtime on every
  // viewport tick.
  const mapStateRef = useRef<unknown>(null);
  // Threads we've already auto-titled this session, so the first-turn title is
  // written exactly once per thread (a fire-and-forget metadata patch).
  const titledThreadIds = useRef<Set<string>>(new Set());
  const selectedField = fields.find((f) => f.id === selectedFieldId) ?? null;
  mapStateRef.current = {
    viewport,
    features: features.map((f) => ({
      id: f.id,
      name: f.name,
      geometry_type: f.geometryType,
    })),
    selected_ids: selectedIds,
    layers: layers.filter((l) => l.visible).map((l) => ({ id: l.id, label: l.label })),
    fields: fields.map((f) => ({ id: f.id, name: f.name, crop: f.crop })),
    // Always carry the id when a field is selected — even if the user has panned
    // it out of the viewport-scoped `fields` list — so the agent can still target
    // it with the field-raster tools.
    selected_field:
      selectedFieldId != null
        ? {
            id: selectedFieldId,
            name: selectedField?.name ?? null,
            crop: selectedField?.crop ?? null,
          }
        : null,
  };

  // The thread-list adapter owns thread creation/listing, scoped to this user.
  // It is keyed only on userId so switching map state never tears it down.
  const threadListAdapter = useMemo(
    () => createLangGraphThreadListAdapter({ client: createClient(), userId }),
    [userId],
  );

  const runtime = useLangGraphRuntime({
    autoCancelPendingToolCalls: true,
    unstable_threadListAdapter: threadListAdapter,
    stream: async function* (messages, { initialize, ...config }) {
      const { externalId } = await initialize();
      if (!externalId) throw new Error("Thread not found");
      // Label new conversations from their first user turn so the sidebar shows
      // something meaningful before the user renames anything. Mark the thread
      // only once we actually have a usable title, so a tool-only first turn
      // doesn't permanently suppress titling; setInitialThreadTitle no-ops when
      // the thread already has a title, so this never overwrites an older,
      // already-named conversation.
      if (!titledThreadIds.current.has(externalId)) {
        const title = deriveThreadTitle(messages);
        if (title) {
          titledThreadIds.current.add(externalId);
          void setInitialThreadTitle(externalId, title).catch(() => {});
        }
      }
      yield* sendMessage({
        threadId: externalId,
        messages,
        config,
        mapState: mapStateRef.current,
      });
    },
    load: async (externalId) => {
      const state = await getThreadState(externalId);
      return {
        messages: (state.values as { messages?: LangChainMessage[] } | undefined)?.messages ?? [],
        interrupts: state.tasks[0]?.interrupts ?? [],
      };
    },
    getCheckpointId,
  });

  return <AssistantRuntimeProvider runtime={runtime}>{children}</AssistantRuntimeProvider>;
}
