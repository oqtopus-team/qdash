import { describe, expect, it } from "vitest";

import {
  buildMuxCellMap,
  buildMuxGroupBoxes,
  buildQidToMux,
  clipMuxBoxes,
  muxLabelAreaClass,
  muxLabelPosition,
  standaloneQids,
  type GridPosition,
} from "@/lib/utils/mux-groups";

// Synthetic, sparse, nonrectangular 10-qubit layout on a 4x5 grid (not
// modeled on any real chip). MUX IDs are sparse; MUX 12 has only two members.
//   row 0: .  0  1  .  .
//   row 1: .  2  3  .  .
//   row 2: 4  5  .  8  9
//   row 3: 6  7  .  .  .
function syntheticLayout(): {
  positions: Record<number, GridPosition>;
  groups: Record<string, number[]>;
} {
  const positions: Record<number, GridPosition> = {
    0: { row: 0, col: 1 },
    1: { row: 0, col: 2 },
    2: { row: 1, col: 1 },
    3: { row: 1, col: 2 },
    4: { row: 2, col: 0 },
    5: { row: 2, col: 1 },
    6: { row: 3, col: 0 },
    7: { row: 3, col: 1 },
    8: { row: 2, col: 3 },
    9: { row: 2, col: 4 },
  };
  const groups: Record<string, number[]> = {
    "3": [0, 1, 2, 3],
    "8": [4, 5, 6, 7],
    "12": [8, 9],
  };
  return { positions, groups };
}

describe("buildMuxGroupBoxes", () => {
  it("places MUX labels on their member qubits, not by grid enumeration", () => {
    const { positions, groups } = syntheticLayout();
    const boxes = buildMuxGroupBoxes(groups, positions);

    expect(boxes.map((box) => box.muxId)).toEqual([3, 8, 12]);
    expect(boxes[0]).toMatchObject({ minRow: 0, maxRow: 1, minCol: 1, maxCol: 2 });
    expect(boxes[1]).toMatchObject({ minRow: 2, maxRow: 3, minCol: 0, maxCol: 1 });
    expect(boxes[2]).toMatchObject({ minRow: 2, maxRow: 2, minCol: 3, maxCol: 4 });

    // Empty cells belong to no MUX, so they get no boundary or label.
    const cells = buildMuxCellMap(boxes, positions);
    for (const empty of ["0,0", "0,3", "1,0", "2,2", "3,3", "3,4"]) {
      expect(cells.get(empty)).toBeUndefined();
    }
    expect(cells.get("0,1")?.muxId).toBe(3);
    expect(cells.get("3,1")?.muxId).toBe(8);
    expect(cells.get("2,4")?.muxId).toBe(12);
  });

  it("keeps sparse MUX IDs and permuted, noncontiguous members", () => {
    const positions: Record<number, GridPosition> = {
      10: { row: 1, col: 1 },
      3: { row: 0, col: 0 },
      7: { row: 0, col: 1 },
      21: { row: 1, col: 0 },
      40: { row: 2, col: 2 },
      41: { row: 2, col: 3 },
    };
    const boxes = buildMuxGroupBoxes({ "17": [10, 3, 21, 7], "5": [41, 40] }, positions);

    expect(boxes.map((box) => box.muxId)).toEqual([5, 17]);
    expect(boxes[1]).toMatchObject({ qids: [10, 3, 21, 7], minRow: 0, maxRow: 1, minCol: 0 });
    expect(buildQidToMux(boxes).get(21)).toBe(17);
    expect(buildQidToMux(boxes).get(40)).toBe(5);
  });

  it("returns no groups without membership or positions", () => {
    expect(buildMuxGroupBoxes(undefined, { 0: { row: 0, col: 0 } })).toEqual([]);
    expect(buildMuxGroupBoxes({ "0": [0] }, undefined)).toEqual([]);
    expect(buildMuxGroupBoxes({ "0": [], "1": [9] }, {})).toEqual([]);
  });

  it("gives partial MUXes no phantom cells and leaves standalone qubits unlabeled", () => {
    // MUX 4 lists three qubits of a 2x2 block; qubit 3 sits in that block but is standalone.
    const positions: Record<number, GridPosition> = {
      0: { row: 0, col: 0 },
      1: { row: 0, col: 1 },
      2: { row: 1, col: 0 },
      3: { row: 1, col: 1 },
      8: { row: 0, col: 3 },
    };
    const muxes = { "4": [2, 0, 1] };
    const boxes = buildMuxGroupBoxes(muxes, positions);
    const cells = buildMuxCellMap(boxes, positions);

    expect(boxes).toHaveLength(1);
    expect(boxes[0]).toMatchObject({ muxId: 4, qids: [2, 0, 1], maxRow: 1, maxCol: 1 });
    expect(cells.get("1,0")?.muxId).toBe(4);
    expect(cells.get("1,1")).toBeUndefined();
    expect(cells.get("0,3")).toBeUndefined();
    expect(buildQidToMux(boxes).has(3)).toBe(false);
    expect(standaloneQids(muxes, positions)).toEqual([3, 8]);
  });

  it("treats an empty muxes declaration as all standalone", () => {
    const positions: Record<number, GridPosition> = {
      0: { row: 0, col: 0 },
      1: { row: 0, col: 1 },
    };

    expect(buildMuxGroupBoxes({}, positions)).toEqual([]);
    expect(standaloneQids({}, positions)).toEqual([0, 1]);
  });
});

describe("clipMuxBoxes", () => {
  it("clips groups to a region zoom window in window-local cells", () => {
    const { positions, groups } = syntheticLayout();
    const boxes = buildMuxGroupBoxes(groups, positions);

    // Top-left 3x3 window: MUX 3 whole, the top row of MUX 8, MUX 12 outside.
    const topLeft = clipMuxBoxes(boxes, { row: 0, col: 0, rows: 3, cols: 3 });
    expect(topLeft).toEqual([
      { muxId: 3, row: 0, col: 1, rows: 2, cols: 2, singleCell: false },
      { muxId: 8, row: 2, col: 0, rows: 1, cols: 2, singleCell: false },
    ]);

    // A window that cuts through MUX 8 and MUX 12 keeps only their visible cells.
    const partial = clipMuxBoxes(boxes, { row: 2, col: 1, rows: 2, cols: 3 });
    expect(partial).toEqual([
      { muxId: 8, row: 0, col: 0, rows: 2, cols: 1, singleCell: false },
      { muxId: 12, row: 0, col: 2, rows: 1, cols: 1, singleCell: true },
    ]);
  });

  it("labels a MUX only when the view shows one of its members", () => {
    // Two far-apart members: the bounding box spans the whole 8x8 grid.
    const positions: Record<number, GridPosition> = {
      0: { row: 0, col: 0 },
      1: { row: 7, col: 7 },
      2: { row: 1, col: 5 },
    };
    const boxes = buildMuxGroupBoxes({ "5": [0, 1] }, positions);

    // The top-right 4x4 window overlaps the box but holds only standalone qubit 2.
    expect(clipMuxBoxes(boxes, { row: 0, col: 4, rows: 4, cols: 4 })).toEqual([]);
    // A window with one member labels just that member's cell.
    expect(clipMuxBoxes(boxes, { row: 4, col: 4, rows: 4, cols: 4 })).toEqual([
      { muxId: 5, row: 3, col: 3, rows: 1, cols: 1, singleCell: true },
    ]);
  });
});

describe("MUX label placement", () => {
  it("centers labels over several cells and anchors single-cell labels at an edge", () => {
    const wide = { muxId: 1, row: 1, col: 2, rows: 2, cols: 2, singleCell: false };
    const single = { muxId: 2, row: 1, col: 2, rows: 1, cols: 1, singleCell: true };

    expect(muxLabelPosition(wide, 40, 4)).toEqual({
      top: 2 * 44 - 2,
      left: 3 * 44 - 2,
      transform: "translate(-50%, -50%)",
    });
    // Bottom-left corner of the cell: clear of the centered value or qubit label.
    expect(muxLabelPosition(single, 40, 4)).toEqual({
      top: 2 * 44 - 4,
      left: 2 * 44,
      transform: "translate(0, -100%)",
    });
    expect(muxLabelAreaClass(wide)).toContain("justify-center");
    expect(muxLabelAreaClass(single)).toContain("items-end");
    expect(muxLabelAreaClass(single)).not.toContain("justify-center");
  });
});
