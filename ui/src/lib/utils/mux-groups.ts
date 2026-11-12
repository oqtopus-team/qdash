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

/** Part of a MUX box inside a view window, in window-local 0-based cells. */
export interface ClippedMuxBox {
  muxId: number;
  row: number;
  col: number;
  rows: number;
  cols: number;
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
      minRow,
      maxRow,
      minCol,
      maxCol,
      isEven: (Math.floor(minRow / span) + Math.floor(minCol / span)) % 2 === 0,
    });
  }
  return boxes.sort((a, b) => a.muxId - b.muxId);
}

/** Clip MUX boxes to a view window; boxes fully outside are dropped. */
export function clipMuxBoxes(boxes: MuxGroupBox[], view: GridWindow): ClippedMuxBox[] {
  const clipped: ClippedMuxBox[] = [];
  for (const box of boxes) {
    const top = Math.max(box.minRow, view.row);
    const left = Math.max(box.minCol, view.col);
    const bottom = Math.min(box.maxRow, view.row + view.rows - 1);
    const right = Math.min(box.maxCol, view.col + view.cols - 1);
    if (top > bottom || left > right) continue;
    clipped.push({
      muxId: box.muxId,
      row: top - view.row,
      col: left - view.col,
      rows: bottom - top + 1,
      cols: right - left + 1,
    });
  }
  return clipped;
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
