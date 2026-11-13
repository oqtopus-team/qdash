/**
 * Custom hook for loading topology configuration from backend.
 *
 * This hook loads the topology definition with explicit qubit positions and
 * coupling connections from the backend.
 */

import { useMemo } from "react";

import { useGetTopologyById } from "@/client/topology/topology";
import {
  buildMuxGroupBoxes,
  buildQidToMux,
  standaloneQids,
  type MuxGroupBox,
} from "@/lib/utils/mux-groups";

// Type definitions matching backend Pydantic models

interface QubitPosition {
  row: number;
  col: number;
}

/** Which template format the normalized `muxes` came from. */
type MuxesSource = "muxes" | "legacy_groups" | "legacy_qid_div_4" | "legacy_disabled";

/**
 * Qubit position fallback for chips without topology positions: the legacy
 * 2x2 MUX block layout. MUX membership never comes from this value.
 */
const LEGACY_MUX_BLOCK_SIZE = 2;

interface VisualizationConfig {
  show_mux_boundaries: boolean;
  region_size: number;
}

type LayoutType = "grid" | "linear" | "hex" | "custom";

type DirectionConvention = "checkerboard_cr" | "unspecified";

interface TopologyDefinition {
  id: string;
  name: string;
  description: string;
  grid_size: number;
  num_qubits: number;
  layout_type: LayoutType;
  direction_convention: DirectionConvention;
  /**
   * MUX ID -> member qubit IDs; the array index is the local slot. Qubits no
   * MUX lists are standalone (not multiplexed).
   */
  muxes: Record<string, number[]>;
  muxes_source?: MuxesSource;
  standalone_qubits?: number[];
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
 *   - muxSize: Legacy 2x2 block size, only for placing qubits without positions
 *   - regionSize: Region size (convenience accessor)
 *   - hasMux: Whether the topology declares at least one MUX
 *   - showMuxBoundaries: Whether to draw MUX boundaries and labels. This is a
 *     rendering choice only; membership always comes from `muxes`.
 *   - muxGroups: MUX groups with their grid bounds, sorted by MUX ID.
 *     Membership comes from the API's `muxes`; nothing is derived from
 *     coordinates or qubit IDs here.
 *   - qidToMux: Qubit ID to MUX ID lookup for `muxGroups`
 *   - standaloneQids: Known qubits that no MUX lists (no MUX label or box)
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
    const apiResponse = axiosResponse?.data as { data?: TopologyDefinition } | undefined;
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

    const muxGroups: MuxGroupBox[] = buildMuxGroupBoxes(topology.muxes, topology.qubits);

    return {
      topology,
      qubits: topology.qubits,
      couplings: topology.couplings,
      gridSize: topology.grid_size,
      numQubits: topology.num_qubits,
      muxSize: LEGACY_MUX_BLOCK_SIZE,
      muxGroups,
      qidToMux: buildQidToMux(muxGroups),
      standaloneQids: topology.standalone_qubits ?? standaloneQids(topology.muxes, topology.qubits),
      muxesSource: (topology.muxes_source ?? "muxes") as MuxesSource,
      regionSize: topology.visualization?.region_size ?? 4,
      hasMux: muxGroups.length > 0,
      showMuxBoundaries: topology.visualization?.show_mux_boundaries ?? false,
      layoutType: (topology.layout_type ?? "grid") as LayoutType,
      directionConvention: (topology.direction_convention ?? "unspecified") as DirectionConvention,
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
