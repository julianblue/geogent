"use client";

import { createElement, useMemo } from "react";
import { useCopilotAction, useCopilotReadable } from "@copilotkit/react-core";
import { useCopilotChatSuggestions } from "@copilotkit/react-ui";

import { useMapState } from "@/components/map/MapStateProvider";
import { addBufferOverlay } from "@/components/map/overlays";
import { BufferPreviewCard } from "@/components/copilot/cards/BufferPreviewCard";
import { ConfirmSaveCard } from "@/components/copilot/cards/ConfirmSaveCard";
import { FeatureListCard } from "@/components/copilot/cards/FeatureListCard";
import { viewportToBboxWkt, wktPolygonToGeoJSON } from "@/lib/geo";

type FeatureRef = { id: number | string; name: string };

export function useGeogentCopilot() {
  const { mapRef, viewport, features, selectedIds, layers, addFeature, upsertLayer } =
    useMapState();

  useCopilotReadable({
    description:
      "Current map viewport (WGS84). Use `bounds` as a bbox polygon for spatial queries on the visible area.",
    value: viewport,
  });

  useCopilotReadable({
    description: "Features currently rendered on the map.",
    value: features.map((f) => ({
      id: f.id,
      name: f.name,
      geometryType: f.geometryType,
    })),
  });

  useCopilotReadable({
    description: "Feature ids the user has explicitly selected.",
    value: selectedIds,
  });

  useCopilotReadable({
    description: "Active map overlays.",
    value: layers.filter((l) => l.visible).map((l) => ({ id: l.id, label: l.label })),
  });

  useCopilotAction({
    name: "flyTo",
    description: "Fly the map to a longitude/latitude with an optional zoom level.",
    parameters: [
      { name: "longitude", type: "number", description: "Longitude in WGS84 degrees." },
      { name: "latitude", type: "number", description: "Latitude in WGS84 degrees." },
      {
        name: "zoom",
        type: "number",
        description: "Target zoom level (0-22). Defaults to 12.",
        required: false,
      },
    ],
    handler: ({ longitude, latitude, zoom }) => {
      mapRef.current?.flyTo({ center: [longitude, latitude], zoom: zoom ?? 12 });
      return `Flew to (${longitude}, ${latitude})`;
    },
  });

  useCopilotAction({
    name: "addBufferLayer",
    description:
      "Buffer a geometry by N meters and overlay the result on the map. If geometryWkt is omitted the current viewport bbox is used.",
    parameters: [
      {
        name: "distanceMeters",
        type: "number",
        description: "Buffer distance in meters (> 0).",
      },
      {
        name: "geometryWkt",
        type: "string",
        description: "Optional input geometry as WKT (SRID 4326).",
        required: false,
      },
    ],
    render: ({ status, args, result }) =>
      createElement(BufferPreviewCard, {
        status,
        distanceMeters: args.distanceMeters ?? 0,
        resultWkt: (result as { buffered_wkt?: string } | undefined)?.buffered_wkt ?? undefined,
      }),
    handler: async ({ distanceMeters, geometryWkt }) => {
      const wkt = geometryWkt ?? viewportToBboxWkt(viewport);
      const res = await fetch("/api/proxy/analytics/buffer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ geometry_wkt: wkt, distance_m: distanceMeters }),
      });
      if (!res.ok) throw new Error(`Buffer failed: ${res.status}`);
      const data = (await res.json()) as { buffered_wkt: string };
      const layerId = `buffer-${Date.now()}`;
      addBufferOverlay(mapRef.current, layerId, data.buffered_wkt);
      upsertLayer({
        id: layerId,
        label: `Buffer ${distanceMeters} m`,
        visible: true,
      });
      return data;
    },
  });

  useCopilotAction({
    name: "listFeaturesInViewport",
    description: "Return features stored in the database that lie inside the current viewport.",
    parameters: [],
    render: ({ status, result }) =>
      createElement(FeatureListCard, {
        status,
        features: (result as { features?: FeatureRef[] } | undefined)?.features,
      }),
    handler: async () => {
      const wkt = viewportToBboxWkt(viewport);
      const res = await fetch("/api/proxy/analytics/features-within", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ geometry_wkt: wkt }),
      });
      if (!res.ok) throw new Error(`features-within failed: ${res.status}`);
      return (await res.json()) as { features: FeatureRef[] };
    },
  });

  useCopilotAction({
    name: "confirmFeatureSave",
    description:
      "Ask the user to confirm saving a feature to the database. Completes only after the user clicks Save or Cancel.",
    parameters: [
      { name: "name", type: "string", description: "Suggested feature name." },
      { name: "geometryWkt", type: "string", description: "Geometry as WKT (SRID 4326)." },
    ],
    renderAndWaitForResponse: ({ args, respond, status }) =>
      createElement(ConfirmSaveCard, {
        status,
        defaultName: args.name ?? "Unnamed feature",
        wkt: args.geometryWkt ?? "",
        onSave: async (finalName: string) => {
          const geometry = wktPolygonToGeoJSON(args.geometryWkt ?? "");
          if (!geometry) {
            respond?.({
              ok: false,
              error: "Only Polygon WKT is supported by this UI for now.",
            });
            return;
          }
          const res = await fetch("/api/proxy/features", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: finalName, geometry, properties: {} }),
          });
          if (!res.ok) {
            respond?.({ ok: false, error: `Save failed: ${res.status}` });
            return;
          }
          const body = (await res.json()) as { id: number };
          addFeature({
            id: String(body.id),
            name: finalName,
            geometryType: geometry.type,
            geometry,
          });
          respond?.({ ok: true, id: body.id });
        },
        onCancel: () => respond?.({ ok: false, cancelled: true }),
      }),
  });

  const hasFeatures = features.length > 0;
  const hasSelection = selectedIds.length > 0;

  useCopilotChatSuggestions(
    useMemo(
      () => ({
        instructions:
          hasFeatures || hasSelection
            ? "Suggest 3 short prompts that operate on the features or layers currently in view, plus one slash-style prompt that starts with '/' (e.g. '/buffer 500 m')."
            : "Suggest 3 short starter prompts for exploring places on the map (e.g. flying to a city), plus one slash-style prompt that starts with '/' (e.g. '/buffer 500 m').",
        minSuggestions: 2,
        maxSuggestions: 4,
      }),
      [hasFeatures, hasSelection],
    ),
    [hasFeatures, hasSelection],
  );
}
