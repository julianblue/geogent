import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { MapStateProvider } from "@/components/map/MapStateProvider";
import { indexCompositeWidget } from "./IndexCompositeWidget";
import type { CompositeResult } from "./shared";

const ok: CompositeResult = {
  ok: true,
  item_id: "S2B_31UDQ_20260501_0_L2A",
  datetime: "2026-05-01T10:30:00Z",
  cloud_cover: 4.2,
  composite: "ndvi",
};

describe("indexCompositeWidget", () => {
  it("registers under 'index-composite' with the composite label as title", () => {
    expect(indexCompositeWidget.type).toBe("index-composite");
    expect(indexCompositeWidget.title?.(ok)).toBe("NDVI (vegetation)");
  });

  it("renders provenance inline for a successful render", () => {
    const { Inline } = indexCompositeWidget;
    render(<Inline id="t1" data={ok} />);
    expect(screen.getByText("NDVI (vegetation)")).toBeInTheDocument();
    expect(screen.getByText(/S2B_31UDQ_20260501_0_L2A/)).toBeInTheDocument();
  });

  it("renders an error card when the scene couldn't be resolved", () => {
    const { Inline } = indexCompositeWidget;
    render(<Inline id="t1" data={{ ok: false, reason: "no cloud-free scene" }} />);
    expect(screen.getByText(/Couldn't render the scene: no cloud-free scene/)).toBeInTheDocument();
  });

  it("renders the expanded switcher (disabled when no live scene) inside MapState", () => {
    const Expanded = indexCompositeWidget.Expanded!;
    render(
      <MapStateProvider>
        <Expanded id="t1" data={ok} />
      </MapStateProvider>,
    );
    expect(screen.getByText("Composite")).toBeInTheDocument();
    expect(screen.getByText(/no longer on the map/)).toBeInTheDocument();
  });
});
