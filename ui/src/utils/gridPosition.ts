/**
 * Grid position utilities for topology-aware qubit/coupling layout.
 *
 * These utilities calculate grid positions for qubits and couplings based on
 * the active topology template configuration. Supports both MUX-based and
 * non-MUX layouts.
 */

export interface GridPosition {
  row: number;
  col: number;
}

export interface TopologyLayoutParams {
  /** Whether MUX grouping is enabled */
  muxEnabled: boolean;
  /** MUX size (e.g., 2 means 2x2 qubits per MUX) */
  muxSize: number;
  /** Total grid size (e.g., 8 for 8x8 grid) */
  gridSize: number;
  /** Layout type for special handling */
  layoutType?: "grid" | "linear" | "hex" | "custom";
}

/**
 * Calculate grid position for a qubit based on topology configuration.
 *
 * For MUX-based layouts (square-lattice-mux):
 *   - Qubits are grouped into MUX units
 *   - Each MUX contains muxSize x muxSize qubits
 *   - Qubit ID determines MUX index and position within MUX
 *
 * For non-MUX layouts (linear, hex):
 *   - Simple row-major ordering
 *
 * @param qid - Qubit identifier (string "Q00" or number 0)
 * @param params - Topology layout parameters
 * @returns Grid position {row, col}
 */
export function getQubitGridPosition(
  qid: string | number,
  params: TopologyLayoutParams,
): GridPosition {
  const qidNum =
    typeof qid === "string" ? parseInt(qid.replace(/\D/g, "")) : qid;

  // Linear layout: single row
  if (params.layoutType === "linear") {
    return {
      row: 0,
      col: qidNum,
    };
  }

  // Non-MUX grid layout: simple row-major
  if (!params.muxEnabled) {
    return {
      row: Math.floor(qidNum / params.gridSize),
      col: qidNum % params.gridSize,
    };
  }

  // MUX-based layout
  const qubitsPerMux = params.muxSize * params.muxSize;
  const muxIndex = Math.floor(qidNum / qubitsPerMux);
  const muxesPerRow = Math.floor(params.gridSize / params.muxSize);
  const muxRow = Math.floor(muxIndex / muxesPerRow);
  const muxCol = muxIndex % muxesPerRow;
  const localIndex = qidNum % qubitsPerMux;
  const localRow = Math.floor(localIndex / params.muxSize);
  const localCol = localIndex % params.muxSize;

  return {
    row: muxRow * params.muxSize + localRow,
    col: muxCol * params.muxSize + localCol,
  };
}

/**
 * Calculate coupling position between two qubits.
 *
 * @param qid1 - First qubit ID (number)
 * @param qid2 - Second qubit ID (number)
 * @param params - Topology layout parameters
 * @returns Position of both qubits {row1, col1, row2, col2}
 */
export function getCouplingPosition(
  qid1: number,
  qid2: number,
  params: TopologyLayoutParams,
): { row1: number; col1: number; row2: number; col2: number } {
  const pos1 = getQubitGridPosition(qid1, params);
  const pos2 = getQubitGridPosition(qid2, params);

  return {
    row1: pos1.row,
    col1: pos1.col,
    row2: pos2.row,
    col2: pos2.col,
  };
}

/**
 * Check if a qubit is within a specific region.
 *
 * Used for region zoom functionality.
 *
 * @param qid - Qubit ID (number)
 * @param regionRow - Region row index
 * @param regionCol - Region column index
 * @param regionSize - Size of each region
 * @param params - Topology layout parameters
 * @returns True if qubit is in the region
 */
export function isQubitInRegion(
  qid: number,
  regionRow: number,
  regionCol: number,
  regionSize: number,
  params: TopologyLayoutParams,
): boolean {
  const pos = getQubitGridPosition(qid, params);
  const regionStartRow = regionRow * regionSize;
  const regionStartCol = regionCol * regionSize;

  return (
    pos.row >= regionStartRow &&
    pos.row < regionStartRow + regionSize &&
    pos.col >= regionStartCol &&
    pos.col < regionStartCol + regionSize
  );
}

/**
 * Get the MUX index for a qubit.
 *
 * @param qid - Qubit ID (number)
 * @param muxSize - MUX size
 * @returns MUX index
 */
export function getMuxIndex(qid: number, muxSize: number): number {
  const qubitsPerMux = muxSize * muxSize;
  return Math.floor(qid / qubitsPerMux);
}

/**
 * Get all qubit IDs in a specific MUX.
 *
 * @param muxIndex - MUX index
 * @param muxSize - MUX size
 * @returns Array of qubit IDs in the MUX
 */
export function getQubitsInMux(muxIndex: number, muxSize: number): number[] {
  const qubitsPerMux = muxSize * muxSize;
  const startQid = muxIndex * qubitsPerMux;
  return Array.from({ length: qubitsPerMux }, (_, i) => startQid + i);
}

/**
 * Calculate the number of MUXes for a given grid size.
 *
 * @param gridSize - Total grid size
 * @param muxSize - MUX size
 * @returns Number of MUXes
 */
export function getMuxCount(gridSize: number, muxSize: number): number {
  const muxesPerRow = Math.floor(gridSize / muxSize);
  return muxesPerRow * muxesPerRow;
}

/**
 * Calculate grid size from chip size.
 *
 * @param chipSize - Number of qubits
 * @returns Grid size (square root for square grids)
 */
export function getGridSizeFromChipSize(chipSize: number): number {
  return Math.floor(Math.sqrt(chipSize));
}

/**
 * Get qubit position from explicit position mapping.
 *
 * This is the preferred method when topology data is available.
 *
 * @param qid - Qubit ID (number)
 * @param qubits - Qubit position mapping from topology
 * @returns Grid position or null if not found
 */
export function getQubitPositionFromMap(
  qid: number,
  qubits: Record<number, GridPosition>,
): GridPosition | null {
  return qubits[qid] || null;
}

/**
 * Get coupling position from explicit position mapping.
 *
 * @param qid1 - First qubit ID
 * @param qid2 - Second qubit ID
 * @param qubits - Qubit position mapping from topology
 * @returns Positions or null if either qubit not found
 */
export function getCouplingPositionFromMap(
  qid1: number,
  qid2: number,
  qubits: Record<number, GridPosition>,
): { row1: number; col1: number; row2: number; col2: number } | null {
  const pos1 = getQubitPositionFromMap(qid1, qubits);
  const pos2 = getQubitPositionFromMap(qid2, qubits);

  if (!pos1 || !pos2) return null;

  return {
    row1: pos1.row,
    col1: pos1.col,
    row2: pos2.row,
    col2: pos2.col,
  };
}

/**
 * Check if a position is within a specific region.
 *
 * @param pos - Grid position
 * @param regionRow - Region row index
 * @param regionCol - Region column index
 * @param regionSize - Size of each region
 * @returns True if position is in the region
 */
export function isPositionInRegion(
  pos: GridPosition,
  regionRow: number,
  regionCol: number,
  regionSize: number,
): boolean {
  const regionStartRow = regionRow * regionSize;
  const regionStartCol = regionCol * regionSize;

  return (
    pos.row >= regionStartRow &&
    pos.row < regionStartRow + regionSize &&
    pos.col >= regionStartCol &&
    pos.col < regionStartCol + regionSize
  );
}

/**
 * Create a reverse lookup map from position to qubit ID.
 *
 * @param qubits - Qubit position mapping
 * @returns Map of "row-col" to qubit ID
 */
export function createPositionToQubitMap(
  qubits: Record<number, GridPosition>,
): Map<string, number> {
  const map = new Map<string, number>();
  Object.entries(qubits).forEach(([qid, pos]) => {
    map.set(`${pos.row}-${pos.col}`, Number(qid));
  });
  return map;
}
