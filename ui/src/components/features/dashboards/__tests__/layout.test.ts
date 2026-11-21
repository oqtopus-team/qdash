import { describe, expect, it } from "vitest";

import type { DashboardPanelModel } from "@/schemas";

import {
  applyLayoutAction,
  canApplyLayoutAction,
  nextPanelLayout,
  resolveCollisions,
  sortPanels,
} from "../layout";

function panel(id: string, x: number, y: number, w = 6, h = 2): DashboardPanelModel {
  return { panel_id: id, type: "markdown", layout: { x, y, w, h }, config: { content: id } };
}

describe("layout helpers", () => {
  it("sorts panels by row, then column", () => {
    const sorted = sortPanels([panel("c", 0, 3), panel("b", 6, 0), panel("a", 0, 0)]);
    expect(sorted.map((entry) => entry.panel_id)).toEqual(["a", "b", "c"]);
  });

  it("keeps x + w within the 12 columns", () => {
    expect(applyLayoutAction({ x: 6, y: 0, w: 6, h: 2 }, "right")).toEqual({
      x: 6,
      y: 0,
      w: 6,
      h: 2,
    });
    expect(canApplyLayoutAction({ x: 6, y: 0, w: 6, h: 2 }, "right")).toBe(false);
    // Growing at the right edge extends the panel to the left instead.
    expect(applyLayoutAction({ x: 6, y: 0, w: 6, h: 2 }, "wider")).toEqual({
      x: 5,
      y: 0,
      w: 7,
      h: 2,
    });
    expect(canApplyLayoutAction({ x: 0, y: 0, w: 12, h: 2 }, "wider")).toBe(false);
    expect(canApplyLayoutAction({ x: 0, y: 0, w: 1, h: 1 }, "narrower")).toBe(false);
    expect(canApplyLayoutAction({ x: 0, y: 0, w: 1, h: 12 }, "taller")).toBe(false);
    expect(canApplyLayoutAction({ x: 0, y: 0, w: 1, h: 1 }, "up")).toBe(false);
  });

  it("pushes overlapped panels below the moved one", () => {
    const moved = [panel("a", 0, 0), panel("b", 0, 2)].map((entry) =>
      entry.panel_id === "b" ? { ...entry, layout: { ...entry.layout, y: 1 } } : entry,
    );
    const resolved = resolveCollisions(moved, "b");
    expect(resolved.find((entry) => entry.panel_id === "b")?.layout.y).toBe(1);
    expect(resolved.find((entry) => entry.panel_id === "a")?.layout.y).toBe(3);
  });

  it("places new panels below every existing panel with type-specific sizes", () => {
    const panels = [panel("a", 0, 0, 6, 3), panel("b", 6, 1, 6, 4)];
    expect(nextPanelLayout(panels, "metric_script")).toEqual({ x: 0, y: 5, w: 6, h: 4 });
    expect(nextPanelLayout(panels, "markdown")).toEqual({ x: 0, y: 5, w: 12, h: 2 });
    expect(nextPanelLayout([], "qubit_metric")).toEqual({ x: 0, y: 0, w: 6, h: 3 });
  });
});
