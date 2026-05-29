import type { WidgetDefinition } from "@/components/assistant/widgets/types";

/**
 * Module-level registry of widget definitions keyed by `type`. Plain map, no
 * hooks — safe to import from server and client. Definitions are registered
 * once at module load via `widgets/index.ts`.
 */
const registry = new Map<string, WidgetDefinition<never>>();

/**
 * Register a widget definition. Re-registering the same `type` overwrites the
 * previous entry (last-write-wins) so hot-reload doesn't accumulate stale defs.
 */
export function registerWidget<TData>(definition: WidgetDefinition<TData>): void {
  registry.set(definition.type, definition as unknown as WidgetDefinition<never>);
}

/** Look up a registered widget definition, or `undefined` if unknown. */
export function getWidget(type: string): WidgetDefinition<never> | undefined {
  return registry.get(type);
}
