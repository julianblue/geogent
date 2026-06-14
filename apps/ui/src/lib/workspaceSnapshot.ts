import { createClient } from "@/lib/chatApi";
import type { MapLayer, Sentinel2Scene, Viewport } from "@/components/map/MapStateProvider";

/**
 * Per-thread workspace snapshot (#20). A geo conversation should "remember its
 * map": reopening a thread restores its viewport, layers, Sentinel-2 overlay,
 * field selection and the set of insights widgets that were open.
 *
 * The snapshot is stored in LangGraph **thread metadata** (alongside the
 * `owner`/`title` tags) — threads already persist there per-user, so there's no
 * new store to stand up. LangGraph merges metadata on update, so writing the
 * `snapshot` key preserves the others (and vice-versa).
 *
 * What is *not* snapshotted: features and feature-selection (transient results
 * of `list_features_in_viewport`, which re-run live) and widget *instance data*
 * (the `{ type, data }` payloads re-register from the replayed transcript — we
 * only need to remember which widget ids were promoted).
 */
export type WorkspaceSnapshot = {
  /** Schema version — bump to invalidate older shapes on read. */
  v: 1;
  viewport: { longitude: number; latitude: number; zoom: number } | null;
  layers: MapLayer[];
  sentinel2Scene: Sentinel2Scene | null;
  selectedFieldId: number | null;
  workspace: {
    openWidgetIds: string[];
    pinnedWidgetIds: string[];
    activeWidgetId: string | null;
  };
};

const SNAPSHOT_KEY = "snapshot";

export type SnapshotInput = {
  viewport: Viewport;
  layers: MapLayer[];
  sentinel2Scene: Sentinel2Scene | null;
  selectedFieldId: number | null;
  openWidgetIds: string[];
  pinnedWidgetIds: string[];
  activeWidgetId: string | null;
};

/** Build a serialisable snapshot from the live provider state. */
export function buildSnapshot(input: SnapshotInput): WorkspaceSnapshot {
  return {
    v: 1,
    viewport: {
      longitude: input.viewport.longitude,
      latitude: input.viewport.latitude,
      zoom: input.viewport.zoom,
    },
    layers: input.layers,
    sentinel2Scene: input.sentinel2Scene,
    selectedFieldId: input.selectedFieldId,
    workspace: {
      openWidgetIds: input.openWidgetIds,
      pinnedWidgetIds: input.pinnedWidgetIds,
      activeWidgetId: input.activeWidgetId,
    },
  };
}

/**
 * Coerce raw thread metadata into a snapshot, tolerating older/garbage shapes
 * by returning `null` (a clean reset) rather than throwing into the restore
 * path. Unknown future versions are also rejected.
 */
export function parseSnapshot(raw: unknown): WorkspaceSnapshot | null {
  if (!raw || typeof raw !== "object") return null;
  const s = raw as Partial<WorkspaceSnapshot>;
  if (s.v !== 1) return null;
  const ws = s.workspace ?? { openWidgetIds: [], pinnedWidgetIds: [], activeWidgetId: null };
  return {
    v: 1,
    viewport: s.viewport ?? null,
    layers: Array.isArray(s.layers) ? s.layers : [],
    sentinel2Scene: s.sentinel2Scene ?? null,
    selectedFieldId: typeof s.selectedFieldId === "number" ? s.selectedFieldId : null,
    workspace: {
      openWidgetIds: Array.isArray(ws.openWidgetIds) ? ws.openWidgetIds : [],
      pinnedWidgetIds: Array.isArray(ws.pinnedWidgetIds) ? ws.pinnedWidgetIds : [],
      activeWidgetId: typeof ws.activeWidgetId === "string" ? ws.activeWidgetId : null,
    },
  };
}

/** Stable structural compare so we skip redundant metadata writes. */
export function snapshotsEqual(a: WorkspaceSnapshot | null, b: WorkspaceSnapshot | null): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

/** True when a snapshot carries no thread-specific state worth persisting. */
export function isEmptySnapshot(s: WorkspaceSnapshot): boolean {
  return (
    s.layers.length === 0 &&
    s.sentinel2Scene === null &&
    s.selectedFieldId === null &&
    s.workspace.openWidgetIds.length === 0 &&
    s.workspace.pinnedWidgetIds.length === 0
  );
}

export async function readSnapshot(threadId: string): Promise<WorkspaceSnapshot | null> {
  const thread = await createClient().threads.get(threadId);
  return parseSnapshot(thread.metadata?.[SNAPSHOT_KEY]);
}

export async function writeSnapshot(threadId: string, snapshot: WorkspaceSnapshot): Promise<void> {
  await createClient().threads.update(threadId, { metadata: { [SNAPSHOT_KEY]: snapshot } });
}
