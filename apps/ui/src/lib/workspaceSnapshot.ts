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
 * path. Unknown future versions are also rejected. Individual fields are
 * sanitized to known-safe shapes so a garbled metadata blob can't feed a
 * non-numeric camera into `map.jumpTo` or a non-object into the layer loop.
 */
export function parseSnapshot(raw: unknown): WorkspaceSnapshot | null {
  if (!raw || typeof raw !== "object") return null;
  const s = raw as Record<string, unknown>;
  if (s.v !== 1) return null;
  const ws = (s.workspace ?? {}) as Record<string, unknown>;
  return {
    v: 1,
    viewport: parseViewport(s.viewport),
    layers: parseLayers(s.layers),
    sentinel2Scene: parseScene(s.sentinel2Scene),
    selectedFieldId:
      typeof s.selectedFieldId === "number" && Number.isFinite(s.selectedFieldId)
        ? s.selectedFieldId
        : null,
    workspace: {
      openWidgetIds: parseIds(ws.openWidgetIds),
      pinnedWidgetIds: parseIds(ws.pinnedWidgetIds),
      activeWidgetId: typeof ws.activeWidgetId === "string" ? ws.activeWidgetId : null,
    },
  };
}

function parseViewport(raw: unknown): WorkspaceSnapshot["viewport"] {
  if (!raw || typeof raw !== "object") return null;
  const v = raw as Record<string, unknown>;
  const { longitude, latitude, zoom } = v;
  if (
    typeof longitude === "number" &&
    Number.isFinite(longitude) &&
    typeof latitude === "number" &&
    Number.isFinite(latitude) &&
    typeof zoom === "number" &&
    Number.isFinite(zoom)
  ) {
    return { longitude, latitude, zoom };
  }
  return null;
}

function isGeoJsonGeometry(v: unknown): v is GeoJSON.Geometry {
  return (
    typeof v === "object" &&
    v !== null &&
    !Array.isArray(v) &&
    typeof (v as Record<string, unknown>).type === "string" &&
    "coordinates" in (v as object)
  );
}

function isFeatureCollection(v: unknown): v is GeoJSON.FeatureCollection {
  return (
    typeof v === "object" &&
    v !== null &&
    !Array.isArray(v) &&
    (v as Record<string, unknown>).type === "FeatureCollection" &&
    Array.isArray((v as Record<string, unknown>).features)
  );
}

function isAggregationSource(src: Record<string, unknown>): boolean {
  return (
    (src.aggKind === "heatmap" || src.aggKind === "hexagon") &&
    (src.weightBy === "count" || src.weightBy === "area") &&
    typeof src.radius === "number" &&
    Number.isFinite(src.radius) &&
    Array.isArray(src.points) &&
    src.points.length > 0 &&
    src.points.every(
      (p) =>
        Array.isArray(p) &&
        p.length === 3 &&
        p.every((n) => typeof n === "number" && Number.isFinite(n)),
    )
  );
}

function parseLayers(raw: unknown): MapLayer[] {
  if (!Array.isArray(raw)) return [];
  const out: MapLayer[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const l = item as Record<string, unknown>;
    if (typeof l.id !== "string" || typeof l.label !== "string") continue;
    const layer: MapLayer = { id: l.id, label: l.label, visible: l.visible !== false };
    if (typeof l.opacity === "number" && Number.isFinite(l.opacity)) layer.opacity = l.opacity;
    const src = l.source as Record<string, unknown> | undefined | null;
    if (src && typeof src === "object") {
      // Validate the geometry shape before keeping a source: corrupt or
      // cross-version metadata must not feed invalid GeoJSON into MapLibre's
      // addSource during restore (which would throw and break hydration).
      if (src.kind === "buffer" && typeof src.wkt === "string") {
        layer.source = { kind: "buffer", wkt: src.wkt };
      } else if (src.kind === "route" && isGeoJsonGeometry(src.geometry)) {
        layer.source = { kind: "route", geometry: src.geometry };
      } else if (src.kind === "isochrone" && isFeatureCollection(src.data)) {
        layer.source = { kind: "isochrone", data: src.data };
      } else if (src.kind === "aggregation" && isAggregationSource(src)) {
        layer.source = {
          kind: "aggregation",
          aggKind: src.aggKind as "heatmap" | "hexagon",
          weightBy: src.weightBy as "count" | "area",
          points: src.points as [number, number, number][],
          radius: src.radius as number,
        };
      } else if (
        src.kind === "fieldMemory" &&
        typeof src.artifactId === "string" &&
        typeof src.band === "string" &&
        src.band.length > 0 &&
        typeof src.colormap === "string" &&
        src.colormap.length > 0 &&
        typeof src.url === "string"
      ) {
        layer.source = {
          kind: "fieldMemory",
          artifactId: src.artifactId,
          band: src.band,
          colormap: src.colormap,
          url: src.url,
        };
      }
    }
    out.push(layer);
  }
  return out;
}

function parseScene(raw: unknown): Sentinel2Scene | null {
  if (!raw || typeof raw !== "object") return null;
  const s = raw as Record<string, unknown>;
  // Minimal shape guard — keep a scene only if it carries the two fields the
  // overlay actually reads (a STAC item + a composite id).
  if (typeof s.compositeId === "string" && s.item && typeof s.item === "object") {
    return raw as Sentinel2Scene;
  }
  return null;
}

function parseIds(raw: unknown): string[] {
  return Array.isArray(raw) ? raw.filter((x): x is string => typeof x === "string") : [];
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
