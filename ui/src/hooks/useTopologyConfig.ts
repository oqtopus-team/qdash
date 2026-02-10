/**
 * Custom hook for loading topology configuration from backend.
 *
 * This hook loads the topology definition with explicit qubit positions and
 * coupling connections from the backend.
 */

import { useMemo } from "react";

import { useGetTopologyById } from "@/client/topology/topology";

// Type definitions matching backend Pydantic models

export interface QubitPosition {
  row: number;
  col: number;
}

export interface MuxConfig {
  enabled: boolean;
  size: number;
}

export interface VisualizationConfig {
  show_mux_boundaries: boolean;
  region_size: number;
}

export type LayoutType = "grid" | "linear" | "hex" | "custom";

export type DirectionConvention = "checkerboard_cr" | "unspecified";

export interface TopologyDefinition {
  id: string;
  name: string;
  description: string;
  grid_size: number;
  num_qubits: number;
  layout_type: LayoutType;
  direction_convention: DirectionConvention;
  mux: MuxConfig;
  qubits: Record<number, QubitPosition>;
  couplings: [number, number][];
  visualization: VisualizationConfig;
}

/**
 * Hook to load topology configuration with explicit positions.
 *
 * @param topologyId - Topology ID to load (e.g., "square-lattice-mux-64")
 * @returns Object containing:
 *   - topology: The complete topology definition
 *   - qubits: Qubit ID to position mapping
 *   - couplings: List of coupling pairs
 *   - gridSize: Grid size
 *   - numQubits: Number of qubits
 *   - muxSize: MUX size (convenience accessor)
 *   - regionSize: Region size (convenience accessor)
 *   - hasMux: Whether MUX is enabled (convenience accessor)
 *   - showMuxBoundaries: Whether to show MUX boundaries (convenience accessor)
 *   - getQubitPosition: Helper to get position for a qubit ID
 *   - isLoading: Loading state
 *   - isError: Error state
 *   - error: Error object if failed
 */
export function useTopologyConfig(topologyId: string) {
  const { data, isLoading, isError, error } = useGetTopologyById(topologyId, {
    query: {
      staleTime: Infinity,
      gcTime: Infinity,
    },
  });

  // Parse and transform topology data
  const parsedData = useMemo(() => {
    const axiosResponse = data as { data?: { data?: TopologyDefinition } };
    const apiResponse = axiosResponse?.data as
      | { data?: TopologyDefinition }
      | undefined;
    const topology = apiResponse?.data;

    if (!topology) {
      return null;
    }

    // Create a position lookup map for quick access (numeric keys)
    const positionMap = new Map<number, QubitPosition>();
    if (topology.qubits) {
      Object.entries(topology.qubits).forEach(([qid, pos]) => {
        positionMap.set(Number(qid), pos);
      });
    }

    // Helper function to get position for a qubit ID
    const getQubitPosition = (qid: number): QubitPosition | null => {
      return positionMap.get(qid) || null;
    };

    return {
      topology,
      qubits: topology.qubits,
      couplings: topology.couplings,
      gridSize: topology.grid_size,
      numQubits: topology.num_qubits,
      muxSize: topology.mux?.size ?? 2,
      regionSize: topology.visualization?.region_size ?? 4,
      hasMux: topology.mux?.enabled ?? false,
      showMuxBoundaries: topology.visualization?.show_mux_boundaries ?? false,
      layoutType: (topology.layout_type ?? "grid") as LayoutType,
      directionConvention: (topology.direction_convention ??
        "unspecified") as DirectionConvention,
      getQubitPosition,
      positionMap,
    };
  }, [data]);

  return {
    ...parsedData,
    isLoading,
    isError,
    error,
  };
}

/**
 * Get grid position for a qubit from explicit position data.
 */
export function getQubitPositionFromTopology(
  qid: number,
  qubits: Record<number, QubitPosition>,
): QubitPosition | null {
  return qubits[qid] || null;
}

/**
 * Get coupling position between two qubits.
 */
export function getCouplingPositionFromTopology(
  qid1: number,
  qid2: number,
  qubits: Record<number, QubitPosition>,
): { row1: number; col1: number; row2: number; col2: number } | null {
  const pos1 = getQubitPositionFromTopology(qid1, qubits);
  const pos2 = getQubitPositionFromTopology(qid2, qubits);

  if (!pos1 || !pos2) return null;

  return {
    row1: pos1.row,
    col1: pos1.col,
    row2: pos2.row,
    col2: pos2.col,
  };
}
