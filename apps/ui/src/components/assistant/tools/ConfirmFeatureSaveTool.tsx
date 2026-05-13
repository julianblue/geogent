"use client";

import { useState } from "react";
import {
  useLangGraphInterruptState,
  useLangGraphSendCommand,
} from "@assistant-ui/react-langgraph";

import { useMapState } from "@/components/map/MapStateProvider";
import { ConfirmSaveCard } from "@/components/copilot/cards/ConfirmSaveCard";
import { wktPolygonToGeoJSON } from "@/lib/geo";

type ConfirmPayload = {
  type: "confirm_feature_save";
  name: string;
  geometry_wkt: string;
};

function isConfirmPayload(value: unknown): value is ConfirmPayload {
  return (
    typeof value === "object" &&
    value !== null &&
    (value as { type?: unknown }).type === "confirm_feature_save"
  );
}

export function ConfirmFeatureSaveTool() {
  const interrupt = useLangGraphInterruptState();
  const sendCommand = useLangGraphSendCommand();
  const { addFeature } = useMapState();
  const [status, setStatus] = useState<"running" | "complete">("running");

  if (!interrupt || !isConfirmPayload(interrupt.value)) return null;
  const payload = interrupt.value;

  async function handleSave(finalName: string) {
    const geometry = wktPolygonToGeoJSON(payload.geometry_wkt);
    if (!geometry) {
      await sendCommand({
        resume: JSON.stringify({
          ok: false,
          error: "Only Polygon WKT is supported by this UI for now.",
        }),
      });
      setStatus("complete");
      return;
    }
    const res = await fetch("/api/proxy/features", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: finalName, geometry, properties: {} }),
    });
    if (!res.ok) {
      await sendCommand({
        resume: JSON.stringify({ ok: false, error: `Save failed: ${res.status}` }),
      });
      setStatus("complete");
      return;
    }
    const body = (await res.json()) as { id: number };
    addFeature({
      id: String(body.id),
      name: finalName,
      geometryType: geometry.type,
      geometry,
    });
    await sendCommand({ resume: JSON.stringify({ ok: true, id: body.id }) });
    setStatus("complete");
  }

  async function handleCancel() {
    await sendCommand({ resume: JSON.stringify({ ok: false, cancelled: true }) });
    setStatus("complete");
  }

  return (
    <ConfirmSaveCard
      status={status}
      defaultName={payload.name}
      wkt={payload.geometry_wkt}
      onSave={handleSave}
      onCancel={handleCancel}
    />
  );
}
