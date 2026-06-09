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
import { dashboardWidget } from "@/components/assistant/widgets/dashboard/DashboardWidget";
import { zonalStatsWidget } from "@/components/assistant/widgets/agriculture/ZonalStatsWidget";
import { indexTimeSeriesWidget } from "@/components/assistant/widgets/agriculture/IndexTimeSeriesWidget";
import { indexCompositeWidget } from "@/components/assistant/widgets/agriculture/IndexCompositeWidget";

registerWidget(bufferWidget);
registerWidget(featureListWidget);
registerWidget(approvalWidget);
registerWidget(dashboardWidget);
registerWidget(zonalStatsWidget);
registerWidget(indexTimeSeriesWidget);
registerWidget(indexCompositeWidget);

export { Widget } from "@/components/assistant/widgets/Widget";
export { InsightsWorkspace } from "@/components/assistant/widgets/InsightsWorkspace";
export { WidgetInstanceProvider } from "@/components/assistant/widgets/WidgetInstanceProvider";
export { registerWidget, getWidget } from "@/components/assistant/widgets/registry";
export type {
  WidgetDefinition,
  WidgetInstance,
  WidgetRenderProps,
} from "@/components/assistant/widgets/types";
