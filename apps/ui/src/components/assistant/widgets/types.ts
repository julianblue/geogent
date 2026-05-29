import type { ComponentType } from "react";

import type { WidgetId } from "@/components/workspace/WorkspaceProvider";

/**
 * Props handed to a widget's inline/expanded renderers. The `id` is the stable
 * per-instance identifier (used for promote/close via WorkspaceProvider) and
 * `data` is the result payload the renderer draws.
 */
export type WidgetRenderProps<TData> = { id: WidgetId; data: TData };

/**
 * A registered widget *definition*, keyed by `type`. The framework's contract
 * — `{ id, inline, expanded?, data }` from issue #16 — is split across two
 * shapes: `Inline`/`Expanded` live here (one definition per type), while `id`
 * and `data` are per-instance (see {@link WidgetInstance}).
 */
export type WidgetDefinition<TData = unknown> = {
  /** Registry key — tool/result/interrupt type, e.g. "buffer". */
  type: string;
  /** Compact renderer shown inline in the chat transcript. */
  Inline: ComponentType<WidgetRenderProps<TData>>;
  /** Full renderer shown in the Insights workspace. Omit for inline-only widgets. */
  Expanded?: ComponentType<WidgetRenderProps<TData>>;
  /** Human label for the workspace tab/header; defaults to `type`. */
  title?: (data: TData) => string;
};

/** A live widget *instance* rendered in a transcript and/or the workspace. */
export type WidgetInstance<TData = unknown> = {
  id: WidgetId;
  type: string;
  data: TData;
};
