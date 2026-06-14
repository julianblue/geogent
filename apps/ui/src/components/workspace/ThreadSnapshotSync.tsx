"use client";

import { useEffect, useRef } from "react";

import { useActiveThread } from "@/components/workspace/ActiveThreadProvider";
import { useMapState } from "@/components/map/MapStateProvider";
import { useWorkspace } from "@/components/workspace/WorkspaceProvider";
import { addBufferOverlay, removeOverlay } from "@/components/map/overlays";
import {
  buildSnapshot,
  readSnapshot,
  snapshotsEqual,
  writeSnapshot,
  type WorkspaceSnapshot,
} from "@/lib/workspaceSnapshot";

const PERSIST_DEBOUNCE_MS = 800;

/**
 * Headless bridge that makes each conversation "remember its map" (#20).
 *
 * - On thread open/switch (once the map is ready) it reads the snapshot from
 *   thread metadata and applies it: viewport, layers (+ buffer overlays),
 *   Sentinel-2 scene, field selection, and which insights widgets were open.
 * - While a thread is active it debounce-persists the current snapshot back to
 *   thread metadata whenever the snapshotted state changes.
 *
 * Lives inside MapState + Workspace + ActiveThread providers and renders
 * nothing. Mirrors the LayerSync pattern: one effect-driven sync component
 * keeps imperative map state aligned with declarative React state.
 */
export function ThreadSnapshotSync() {
  const { activeThreadId } = useActiveThread();
  const {
    mapRef,
    mapReady,
    viewport,
    layers,
    replaceLayers,
    sentinel2Scene,
    setSentinel2Scene,
    selectedFieldId,
    selectField,
  } = useMapState();
  const {
    openWidgetIds,
    pinnedWidgetIds,
    activeWidgetId,
    restore: restoreWorkspace,
  } = useWorkspace();

  // Latest layer list, so the restore path can tear down the previous thread's
  // overlays without taking `layers` as an effect dependency (which would
  // re-run the restore on every layer edit).
  const layersRef = useRef(layers);
  layersRef.current = layers;

  // Which thread we've already restored, so switching back and forth doesn't
  // re-restore (and clobber live edits) and so persistence only starts after
  // the active thread has been hydrated.
  const restoredThreadRef = useRef<string | null>(null);
  const restoringRef = useRef(false);
  const lastPersistedRef = useRef<WorkspaceSnapshot | null>(null);

  // Restore on thread open / switch. Gated on mapReady because applying a
  // viewport (imperative jumpTo) and repainting buffer overlays both need the
  // live MapLibre instance.
  useEffect(() => {
    if (!activeThreadId || !mapReady) return;
    if (restoredThreadRef.current === activeThreadId) return;
    const threadId = activeThreadId;
    restoredThreadRef.current = threadId;
    restoringRef.current = true;
    let cancelled = false;

    void (async () => {
      let snapshot: WorkspaceSnapshot | null = null;
      try {
        snapshot = await readSnapshot(threadId);
      } catch {
        // Best-effort: a failed read falls through to a clean reset so a stale
        // map from the previous thread never leaks into this one.
      }
      if (cancelled || restoredThreadRef.current !== threadId) return;

      // Tear down the outgoing thread's buffer overlays before swapping state.
      for (const layer of layersRef.current) {
        removeOverlay(mapRef.current, layer.id);
      }

      const nextLayers = snapshot?.layers ?? [];
      for (const layer of nextLayers) {
        if (layer.source?.kind === "buffer") {
          addBufferOverlay(mapRef.current, layer.id, layer.source.wkt);
        }
      }
      replaceLayers(nextLayers);
      setSentinel2Scene(snapshot?.sentinel2Scene ?? null);
      selectField(snapshot?.selectedFieldId ?? null);
      restoreWorkspace({
        openWidgetIds: snapshot?.workspace.openWidgetIds ?? [],
        pinnedWidgetIds: snapshot?.workspace.pinnedWidgetIds ?? [],
        activeWidgetId: snapshot?.workspace.activeWidgetId ?? null,
      });

      const camera = snapshot?.viewport;
      const map = mapRef.current?.getMap();
      if (camera && map) {
        map.jumpTo({ center: [camera.longitude, camera.latitude], zoom: camera.zoom });
      }

      // Seed the dedupe baseline so the persist effect doesn't immediately
      // write the just-restored snapshot back.
      lastPersistedRef.current = snapshot;
      restoringRef.current = false;
    })();

    return () => {
      cancelled = true;
    };
    // restoreWorkspace/replaceLayers/etc. are stable; intentionally keyed only
    // on the thread + map readiness so restore runs once per opened thread.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeThreadId, mapReady]);

  // Persist (debounced) once the active thread has been restored.
  useEffect(() => {
    if (!activeThreadId || restoringRef.current) return;
    if (restoredThreadRef.current !== activeThreadId) return;

    const snapshot = buildSnapshot({
      viewport,
      layers,
      sentinel2Scene,
      selectedFieldId,
      openWidgetIds,
      pinnedWidgetIds,
      activeWidgetId,
    });
    if (snapshotsEqual(snapshot, lastPersistedRef.current)) return;

    const threadId = activeThreadId;
    const timer = setTimeout(() => {
      lastPersistedRef.current = snapshot;
      void writeSnapshot(threadId, snapshot).catch(() => {
        // Snapshotting is best-effort; a failed write just means this thread
        // reopens with its last successfully-saved state.
      });
    }, PERSIST_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [
    activeThreadId,
    viewport,
    layers,
    sentinel2Scene,
    selectedFieldId,
    openWidgetIds,
    pinnedWidgetIds,
    activeWidgetId,
  ]);

  return null;
}
