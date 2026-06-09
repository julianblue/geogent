"use client";

import { useRef } from "react";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { useLangGraphRuntime, type LangChainMessage } from "@assistant-ui/react-langgraph";

import { useMapState } from "@/components/map/MapStateProvider";
import { createThread, getCheckpointId, getThreadState, sendMessage } from "@/lib/chatApi";

export function RuntimeProvider({ children }: { children: React.ReactNode }) {
  const { viewport, features, selectedIds, fields, selectedFieldId, layers } = useMapState();
  // Snapshot the latest map state into a ref so the async stream callback
  // always reads the freshest value without recreating the runtime on every
  // viewport tick.
  const mapStateRef = useRef<unknown>(null);
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

  const runtime = useLangGraphRuntime({
    autoCancelPendingToolCalls: true,
    stream: async function* (messages, { initialize, ...config }) {
      const { externalId } = await initialize();
      if (!externalId) throw new Error("Thread not found");
      yield* sendMessage({
        threadId: externalId,
        messages,
        config,
        mapState: mapStateRef.current,
      });
    },
    create: async () => {
      const { thread_id } = await createThread();
      return { externalId: thread_id };
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
