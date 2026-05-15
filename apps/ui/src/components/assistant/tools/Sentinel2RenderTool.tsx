"use client";

import { useEffect, useRef } from "react";
import {
  useLangGraphInterruptState,
  useLangGraphSendCommand,
} from "@assistant-ui/react-langgraph";

import { useMapState } from "@/components/map/MapStateProvider";
import {
  COMPOSITE_IDS,
  isCompositeId,
  type CompositeId,
} from "@/lib/sentinel2-presets";
import {
  fetchSentinel2ById,
  findLatestSentinel2,
  type Bbox,
  type Sentinel2Item,
} from "@/lib/sentinel2";

/**
 * Interrupt payload emitted by the agent's `show_sentinel2_scene` tool.
 * Shape mirrors {@link `apps/agent/src/geogent_agent/tools/frontend_actions.py`}.
 */
type RenderPayload = {
  type: "show_sentinel2_scene";
  item_id?: string | null;
  bbox?: number[] | null;
  composite?: string;
};

function isRenderPayload(value: unknown): value is RenderPayload {
  return (
    typeof value === "object" &&
    value !== null &&
    (value as { type?: unknown }).type === "show_sentinel2_scene"
  );
}

function isValidBbox(b: unknown): b is Bbox {
  return Array.isArray(b) && b.length === 4 && b.every((n) => typeof n === "number");
}

function resolveCompositeId(requested: string | undefined): CompositeId {
  // Default to the first preset (true-color) on a typo or missing arg —
  // better than throwing and forcing the agent into a retry loop.
  return isCompositeId(requested) ? requested : COMPOSITE_IDS[0];
}

/**
 * Auto-handler for the agent's `show_sentinel2_scene` interrupt.
 *
 * Unlike {@link ConfirmFeatureSaveTool}, this has no UI — when the agent
 * asks for a render, we just do it: resolve the STAC item (by id or bbox),
 * push it into MapState (which Sentinel2Overlay subscribes to), then resume
 * the graph with a structured result the agent can describe.
 *
 * Only one interrupt is in flight at a time, so a single-slot ref is enough
 * to dedupe replays from React strict-mode double-mount.
 */
export function Sentinel2RenderTool() {
  const interrupt = useLangGraphInterruptState();
  const sendCommand = useLangGraphSendCommand();
  const { setSentinel2Scene } = useMapState();
  const lastHandledKey = useRef<string | null>(null);

  useEffect(() => {
    if (!interrupt || !isRenderPayload(interrupt.value)) return;
    const interruptKey = JSON.stringify({ value: interrupt.value, ns: interrupt.ns });
    if (lastHandledKey.current === interruptKey) return;
    lastHandledKey.current = interruptKey;

    const payload = interrupt.value;

    void (async () => {
      try {
        let item: Sentinel2Item | null = null;
        if (payload.item_id) {
          item = await fetchSentinel2ById(payload.item_id);
        } else if (isValidBbox(payload.bbox)) {
          item = await findLatestSentinel2(payload.bbox);
        } else {
          throw new Error("show_sentinel2_scene needs either item_id or bbox");
        }

        if (!item) {
          await sendCommand({
            resume: JSON.stringify({
              ok: false,
              reason: payload.item_id
                ? `STAC item ${payload.item_id} not found`
                : "no cloud-free scene matched the bbox",
            }),
          });
          return;
        }

        const compositeId = resolveCompositeId(payload.composite);
        setSentinel2Scene({ item, compositeId });

        await sendCommand({
          resume: JSON.stringify({
            ok: true,
            item_id: item.id,
            datetime: item.datetime,
            cloud_cover: item.cloudCover,
            composite: compositeId,
          }),
        });
      } catch (err) {
        await sendCommand({
          resume: JSON.stringify({
            ok: false,
            reason: err instanceof Error ? err.message : String(err),
          }),
        });
      }
    })();
  }, [interrupt, sendCommand, setSentinel2Scene]);

  return null;
}
