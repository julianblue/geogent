/**
 * Widget framework public surface + one-time registration.
 *
 * Importing this module registers every built-in widget definition. Adding a
 * new widget is a two-step change: create its `*Widget.tsx` definition, then
 * register it here.
 */
import { registerWidget } from "@/components/assistant/widgets/registry";
import { bufferWidget } from "@/components/assistant/widgets/BufferWidget";
import { featureListWidget } from "@/components/assistant/widgets/FeatureListWidget";
import { approvalWidget } from "@/components/assistant/widgets/ApprovalWidget";

registerWidget(bufferWidget);
registerWidget(featureListWidget);
registerWidget(approvalWidget);

export { Widget } from "@/components/assistant/widgets/Widget";
export { InsightsWorkspace } from "@/components/assistant/widgets/InsightsWorkspace";
export { WidgetInstanceProvider } from "@/components/assistant/widgets/WidgetInstanceProvider";
export { registerWidget, getWidget } from "@/components/assistant/widgets/registry";
export type {
  WidgetDefinition,
  WidgetInstance,
  WidgetRenderProps,
} from "@/components/assistant/widgets/types";
