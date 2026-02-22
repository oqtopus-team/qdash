/**
 * Grid position utilities for topology-aware qubit/coupling layout.
 *
 * These utilities calculate grid positions for qubits and couplings based on
 * the active topology template configuration. Supports both MUX-based and
 * non-MUX layouts.
 */

interface GridPosition {
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
