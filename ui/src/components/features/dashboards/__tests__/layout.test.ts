import { describe, expect, it } from "vitest";

import type { DashboardPanelModel } from "@/schemas";

import {
  applyLayoutAction,
  canApplyLayoutAction,
  nextPanelLayout,
  clampLayout,
  resolveCollisions,
  settlePlacements,
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

  it("settles placements deterministically and leaves a valid layout untouched", () => {
    const stored = [
      { id: "a", layout: { x: 0, y: 0, w: 6, h: 2 } },
      // A gap above "b" is kept: nothing is compacted.
      { id: "b", layout: { x: 6, y: 3, w: 6, h: 2 } },
    ];
    const settled = settlePlacements(stored);
    expect(settled).toEqual(stored);
    expect(settled[0]).toBe(stored[0]);
    expect(settled[1]).toBe(stored[1]);

    // "a" pinned over "b" and "c": both move below it, "c" below "b", in reading order.
    const moved = settlePlacements(
      [
        { id: "b", layout: { x: 0, y: 2, w: 12, h: 2 } },
        { id: "a", layout: { x: 0, y: 1, w: 12, h: 3 } },
        { id: "c", layout: { x: 6, y: 4, w: 6, h: 1 } },
      ],
      "a",
    );
    expect(moved.map((item) => item.id)).toEqual(["b", "a", "c"]);
    expect(moved.map((item) => item.layout.y)).toEqual([4, 1, 6]);
  });

  it("clamps a layout into the 12 columns and the 12-row height limit", () => {
    expect(clampLayout({ x: 10, y: -1, w: 6, h: 20 })).toEqual({ x: 6, y: 0, w: 6, h: 12 });
    expect(clampLayout({ x: 0, y: 0, w: 0, h: 0 })).toEqual({ x: 0, y: 0, w: 1, h: 1 });
  });

  it("places new panels below every existing panel with type-specific sizes", () => {
    const panels = [panel("a", 0, 0, 6, 3), panel("b", 6, 1, 6, 4)];
    expect(nextPanelLayout(panels, "metric_script")).toEqual({ x: 0, y: 5, w: 6, h: 4 });
    expect(nextPanelLayout(panels, "markdown")).toEqual({ x: 0, y: 5, w: 12, h: 2 });
    expect(nextPanelLayout([], "qubit_metric")).toEqual({ x: 0, y: 0, w: 6, h: 3 });
  });
});
