/**
 * MUX group geometry derived from the topology's MUX membership.
 *
 * The backend topology API returns the normalized `muxes` (MUX ID -> member
 * qubit IDs in local slot order), keyed by the MUX ID used by the schedulers
 * and `wiring.yaml`. Qubits that no MUX lists are standalone and belong to no
 * box. Labels use the MUX ID; boxes come from member positions, so a layout
 * with missing corners or standalone qubits gets no phantom MUX.
 */

export interface GridPosition {
  row: number;
  col: number;
}

export interface MuxGroupBox {
  /** MUX ID from the topology (may be sparse) */
  muxId: number;
  /** Member qubit IDs in local slot order */
  qids: number[];
  /** Grid cells of the positioned members */
  cells: GridPosition[];
  minRow: number;
  maxRow: number;
  minCol: number;
  maxCol: number;
  /** Checkerboard parity of the box, for alternating boundary colors */
  isEven: boolean;
}

/** A view window on the chip grid (region zoom or the full grid). */
export interface GridWindow {
  row: number;
  col: number;
  rows: number;
  cols: number;
}

/**
 * The visible members of a MUX inside a view window, in window-local 0-based
 * cells: the bounding box of the member cells that the window shows.
 */
export interface ClippedMuxBox {
  muxId: number;
  row: number;
  col: number;
  rows: number;
  cols: number;
  /**
   * The label covers a single cell, whose center holds that cell's own value
   * or qubit label. Anchor the MUX label at the cell's bottom-left edge
   * instead of centering it (see {@link muxLabelPosition}).
   */
  singleCell: boolean;
}

/** The API's `muxes`: MUX ID -> member qubit IDs in local slot order. */
export type RawMuxes = Record<string, number[] | undefined> | null | undefined;

/**
 * Build one box per MUX from the API's `muxes` and qubit positions.
 *
 * Members keep their slot order (never sorted). Members without a position
 * are ignored; a MUX with no positioned member produces no box. The box
 * parity, used only to alternate boundary colors, comes from the box's own
 * extent rather than a fixed MUX size.
 */
export function buildMuxGroupBoxes(
  muxes: RawMuxes,
  positions: Record<number, GridPosition> | null | undefined,
): MuxGroupBox[] {
  if (!muxes || !positions) return [];
  const boxes: MuxGroupBox[] = [];
  for (const [key, members] of Object.entries(muxes)) {
    const muxId = Number(key);
    const qids = Array.isArray(members) ? members : [];
    if (!Number.isInteger(muxId) || qids.length === 0) continue;
    const placed = qids
      .map((qid) => positions[qid])
      .filter((pos): pos is GridPosition => pos !== undefined && pos !== null);
    if (placed.length === 0) continue;
    const minRow = Math.min(...placed.map((pos) => pos.row));
    const minCol = Math.min(...placed.map((pos) => pos.col));
    const maxRow = Math.max(...placed.map((pos) => pos.row));
    const maxCol = Math.max(...placed.map((pos) => pos.col));
    const span = Math.max(maxRow - minRow + 1, maxCol - minCol + 1);
    boxes.push({
      muxId,
      qids: [...qids],
      cells: placed.map((pos) => ({ row: pos.row, col: pos.col })),
      minRow,
      maxRow,
      minCol,
      maxCol,
      isEven: (Math.floor(minRow / span) + Math.floor(minCol / span)) % 2 === 0,
    });
  }
  return boxes.sort((a, b) => a.muxId - b.muxId);
}

/**
 * Clip MUX boxes to a view window.
 *
 * A MUX is labeled only when the window shows at least one of its members, and
 * its label covers just the visible members. A window that overlaps the MUX's
 * bounding box but holds none of its members (empty cells or standalone
 * qubits) gets no label.
 */
export function clipMuxBoxes(boxes: MuxGroupBox[], view: GridWindow): ClippedMuxBox[] {
  const clipped: ClippedMuxBox[] = [];
  for (const box of boxes) {
    const visible = box.cells.filter(
      (cell) =>
        cell.row >= view.row &&
        cell.row < view.row + view.rows &&
        cell.col >= view.col &&
        cell.col < view.col + view.cols,
    );
    if (visible.length === 0) continue;
    const top = Math.min(...visible.map((cell) => cell.row));
    const left = Math.min(...visible.map((cell) => cell.col));
    const rows = Math.max(...visible.map((cell) => cell.row)) - top + 1;
    const cols = Math.max(...visible.map((cell) => cell.col)) - left + 1;
    clipped.push({
      muxId: box.muxId,
      row: top - view.row,
      col: left - view.col,
      rows,
      cols,
      singleCell: rows === 1 && cols === 1,
    });
  }
  return clipped;
}

/** Absolute position of a MUX label over cells of `cellSize` separated by `gap`. */
export interface MuxLabelPosition {
  top: number;
  left: number;
  transform: string;
}

/**
 * Where to place a MUX label in an absolutely positioned overlay.
 *
 * A label over several cells sits at the center of the visible members. A
 * single-cell label sits at the cell's bottom-left edge, a corner that the
 * grids leave free (the qubit label is top-left, units top-right, the status
 * mark bottom-right), so it never covers the value centered in the cell.
 */
export function muxLabelPosition(
  box: ClippedMuxBox,
  cellSize: number,
  gap: number,
): MuxLabelPosition {
  const pitch = cellSize + gap;
  if (box.singleCell) {
    return {
      top: (box.row + 1) * pitch - gap,
      left: box.col * pitch,
      transform: "translate(0, -100%)",
    };
  }
  return {
    top: (box.row + box.rows / 2) * pitch - gap / 2,
    left: (box.col + box.cols / 2) * pitch - gap / 2,
    transform: "translate(-50%, -50%)",
  };
}

/**
 * Tailwind classes that place a MUX label inside its CSS grid area:
 * centered over several cells, at the bottom-left edge of a single cell.
 */
export function muxLabelAreaClass(box: ClippedMuxBox): string {
  return box.singleCell ? "flex items-end justify-start p-0.5" : "flex items-center justify-center";
}

/** Qubit ID -> MUX ID lookup. */
export function buildQidToMux(boxes: MuxGroupBox[]): Map<number, number> {
  const map = new Map<number, number>();
  boxes.forEach((box) => box.qids.forEach((qid) => map.set(qid, box.muxId)));
  return map;
}

/**
 * `"row,col"` -> MUX box of the member qubit at that cell, for per-cell
 * lookups on large grids.
 *
 * Only member cells are mapped: a standalone qubit or an empty cell inside a
 * MUX's bounding box is not part of that MUX.
 */
export function buildMuxCellMap(
  boxes: MuxGroupBox[],
  positions: Record<number, GridPosition> | null | undefined,
): Map<string, MuxGroupBox> {
  const map = new Map<string, MuxGroupBox>();
  if (!positions) return map;
  boxes.forEach((box) => {
    box.qids.forEach((qid) => {
      const pos = positions[qid];
      if (pos && !map.has(`${pos.row},${pos.col}`)) map.set(`${pos.row},${pos.col}`, box);
    });
  });
  return map;
}

/** Known qubits that no MUX lists, in ascending ID order. */
export function standaloneQids(
  muxes: RawMuxes,
  positions: Record<number, GridPosition> | null | undefined,
): number[] {
  if (!positions) return [];
  const members = new Set<number>();
  Object.values(muxes ?? {}).forEach((qids) => (qids ?? []).forEach((qid) => members.add(qid)));
  return Object.keys(positions)
    .map(Number)
    .filter((qid) => !members.has(qid))
    .sort((a, b) => a - b);
}
