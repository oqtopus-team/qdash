"use client";

import { useListChips, useFetchChip } from "@/client/chip/chip";
import { ChipResponse, NodeInfo, EdgeInfo } from "@/schemas";
import { useEffect, useState } from "react";
import Select from "react-select";
import { GraphCanvas } from "reagraph";

// Define types for reagraph nodes and edges
interface NodePositionArgs {
  nodes: any[];
}

interface QubitNode {
  id: string;
  label: string;
  fill?: string;
  size?: number;
  data: {
    position: { x: number; y: number };
    status: string;
    isCalibrated: boolean;
    qubitData?: Record<
      string,
      {
        value: number;
        unit?: string;
        description?: string;
        calibrated_at: string;
        execution_id?: string;
      }
    >;
  };
}

interface QubitEdge {
  id: string;
  source: string;
  target: string;
  label?: string;
  fill?: string;
}

// Types for API data
interface QubitData {
  qid: string;
  status: string;
  data: Record<
    string,
    {
      value: number;
      unit?: string;
      description?: string;
      calibrated_at: string;
      execution_id?: string;
    }
  >;
  node_info: NodeInfo;
}

interface CouplingData {
  qid: string;
  status: string;
  chip_id: string;
  data: Record<string, any>;
  edge_info: EdgeInfo;
}

const TopologyVisualization = ({
  chipData,
  onNodeClick,
  onNodeHover,
  onEdgeHover,
}: {
  chipData: ChipResponse;
  onNodeClick: (qubitId: string) => void;
  onNodeHover: (node: QubitNode | null) => void;
  onEdgeHover: (edge: QubitEdge | null) => void;
}) => {
  if (!chipData.qubits || !chipData.couplings) return null;

  const [nodes, setNodes] = useState<QubitNode[]>([]);
  const [edges, setEdges] = useState<QubitEdge[]>([]);

  // Initialize nodes from qubit data
  useEffect(() => {
    if (!chipData.qubits) return;

    const newNodes = Object.entries(
      chipData.qubits as Record<string, QubitData>
    ).map(([id, qubit]) => {
      const isCalibrated = qubit.data && Object.keys(qubit.data).length > 0;

      // Use position from API
      const x = qubit.node_info.position.x;
      const y = qubit.node_info.position.y;

      return {
        id,
        label: id,
        size: 20,
        fill: isCalibrated ? "#4CAF50" : "#ccc",
        data: {
          position: { x, y },
          status: qubit.status,
          isCalibrated,
          qubitData: qubit.data,
        },
      };
    });

    setNodes(newNodes);
  }, [chipData.qubits]);

  // Convert couplings to edges
  useEffect(() => {
    if (!chipData.couplings) return;

    const newEdges = Object.entries(
      chipData.couplings as Record<string, CouplingData>
    ).map(([id, coupling]) => ({
      id,
      source: coupling.edge_info.source,
      target: coupling.edge_info.target,
      fill: "#666",
    }));

    setEdges(newEdges);
  }, [chipData.couplings]);

  // Custom node position function for reagraph - uses the node's position data
  const getNodePosition = (id: string, { nodes }: NodePositionArgs) => {
    const idx = nodes.findIndex((n) => n.id === id);
    if (idx !== -1 && nodes[idx].data.position) {
      return {
        x: nodes[idx].data.position.x,
        y: nodes[idx].data.position.y,
        z: 1,
      };
    }
    return { x: 0, y: 0, z: 1 };
  };

  const handleNodePointerOver = (node: any) => {
    onNodeHover(node);
    onEdgeHover(null);
  };

  const handleEdgePointerOver = (edge: any) => {
    onEdgeHover(edge);
    onNodeHover(null);
  };

  const handleNodeClick = (node: any) => {
    if (node) {
      onNodeClick(node.id);
    }
  };

  return (
    <div style={{ height: "400px" }}>
      <GraphCanvas
        // @ts-ignore - Ignore TypeScript errors for edge arrow position
        edgeArrowPosition="none"
        // @ts-ignore - Ignore TypeScript errors for custom layout
        layoutType="custom"
        // @ts-ignore - Ignore TypeScript errors for layout overrides
        layoutOverrides={{ getNodePosition }}
        nodes={nodes}
        edges={edges}
        // @ts-ignore - Ignore TypeScript errors for node pointer over
        onNodePointerOver={handleNodePointerOver}
        // @ts-ignore - Ignore TypeScript errors for edge pointer over
        onEdgePointerOver={handleEdgePointerOver}
        // @ts-ignore - Ignore TypeScript errors for node click handler
        onNodeClick={handleNodeClick}
      />
    </div>
  );
};

// Calibration details component
const CalibrationDetails = ({ qubit }: { qubit: QubitData }) => {
  if (!qubit || !qubit.data || Object.keys(qubit.data).length === 0) {
    return <div>No calibration data available</div>;
  }

  return (
    <div className="space-y-4">
      {Object.entries(qubit.data).map(([key, value]: [string, any]) => (
        <div key={key} className="card bg-base-200 shadow-sm">
          <div className="card-body p-4">
            <h3 className="card-title text-sm">{key}</h3>
            <div className="text-sm">
              <p>
                Value: {value.value} {value.unit}
              </p>
              <p>Description: {value.description}</p>
              <p>
                Calibrated at: {new Date(value.calibrated_at).toLocaleString()}
              </p>
              {value.execution_id && <p>Execution ID: {value.execution_id}</p>}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
};

// Calculate calibration metrics
const calculateMetrics = (qubits: Record<string, QubitData>) => {
  const totalQubits = Object.keys(qubits).length;
  const calibratedQubits = Object.values(qubits).filter(
    (q) => q.data && Object.keys(q.data).length > 0
  ).length;

  const averageGateFidelity =
    Object.values(qubits).reduce((sum, q) => {
      const fidelity = q.data?.average_gate_fidelity?.value;
      return fidelity ? sum + fidelity : sum;
    }, 0) / calibratedQubits;

  const averageT1 =
    Object.values(qubits).reduce((sum, q) => {
      const t1 = q.data?.t1?.value;
      return t1 ? sum + t1 : sum;
    }, 0) / calibratedQubits;

  return {
    totalQubits,
    calibratedQubits,
    calibrationPercentage: (calibratedQubits / totalQubits) * 100,
    averageGateFidelity: averageGateFidelity || 0,
    averageT1: averageT1 || 0,
  };
};

// Summary metrics component
const CalibrationSummary = ({
  metrics,
}: {
  metrics: ReturnType<typeof calculateMetrics>;
}) => {
  return (
    <div className="stats shadow w-full bg-base-200">
      <div className="stat">
        <div className="stat-title">Calibration Progress</div>
        <div className="stat-value text-primary">
          {metrics.calibrationPercentage.toFixed(1)}%
        </div>
        <div className="stat-desc">
          {metrics.calibratedQubits} of {metrics.totalQubits} qubits
        </div>
      </div>
      <div className="stat">
        <div className="stat-title">Avg Gate Fidelity</div>
        <div className="stat-value text-primary">
          {(metrics.averageGateFidelity * 100).toFixed(2)}%
        </div>
        <div className="stat-desc">Across calibrated qubits</div>
      </div>
      <div className="stat">
        <div className="stat-title">Avg T1 Time</div>
        <div className="stat-value text-primary">
          {(metrics.averageT1 / 1000).toFixed(2)}μs
        </div>
        <div className="stat-desc">Across calibrated qubits</div>
      </div>
    </div>
  );
};

export const ChipMetrics = () => {
  const [selectedChipId, setSelectedChipId] = useState<string>("");
  const [selectedQubitId, setSelectedQubitId] = useState<string | null>(null);
  const [hoveredNode, setHoveredNode] = useState<QubitNode | null>(null);
  const [hoveredEdge, setHoveredEdge] = useState<QubitEdge | null>(null);

  const {
    data: chips,
    isLoading: isChipsLoading,
    isError: isChipsError,
  } = useListChips();

  const {
    data: chipData,
    isLoading: isChipLoading,
    isError: isChipError,
    refetch: refetchChip,
  } = useFetchChip(selectedChipId, {
    query: {
      enabled: !!selectedChipId,
    },
  });

  useEffect(() => {
    if (chips?.data && chips.data.length > 0 && !selectedChipId) {
      setSelectedChipId(chips.data[0].chip_id);
    }
  }, [chips, selectedChipId]);

  useEffect(() => {
    if (selectedChipId) {
      refetchChip();
    }
  }, [selectedChipId, refetchChip]);

  if (isChipsLoading || isChipLoading) return <div>Loading...</div>;
  if (isChipsError || isChipError) return <div>Error loading data</div>;

  const chipOptions =
    chips?.data?.map((chip: ChipResponse) => ({
      value: chip.chip_id,
      label: chip.chip_id,
    })) || [];

  const selectedQubit =
    selectedQubitId &&
    (chipData?.data?.qubits?.[selectedQubitId] as QubitData | undefined);

  const metrics = chipData?.data?.qubits
    ? calculateMetrics(chipData.data.qubits as Record<string, QubitData>)
    : null;

  return (
    <div className="card bg-base-100 shadow-xl">
      <div className="card-body">
        <div className="flex justify-between items-center mb-4">
          <h2 className="card-title">Calibration Status</h2>
          <Select
            options={chipOptions}
            value={chipOptions.find(
              (option) => option.value === selectedChipId
            )}
            onChange={(option) => {
              setSelectedChipId(option?.value || "");
              setSelectedQubitId(null);
            }}
            className="w-1/3"
          />
        </div>

        {metrics && <CalibrationSummary metrics={metrics} />}

        <div className="flex gap-6 mt-6">
          <div className="w-1/2 card bg-base-100 shadow-xl">
            <div className="card-body p-0">
              {chipData?.data && (
                <TopologyVisualization
                  chipData={chipData.data}
                  onNodeClick={(qubitId) => setSelectedQubitId(qubitId)}
                  onNodeHover={setHoveredNode}
                  onEdgeHover={setHoveredEdge}
                />
              )}
            </div>
          </div>
          <div className="w-1/2 h-[400px]">
            <div className="card bg-base-100 shadow-xl h-full">
              <div className="card-body h-full overflow-y-auto relative">
                <div className="sticky top-0 left-0 right-0 z-20 bg-base-100 -mx-8 px-8 -mt-6 pt-6">
                  <div className="pb-4">
                    <h3 className="text-lg font-bold mb-4">
                      {hoveredNode
                        ? `Qubit ${hoveredNode.id}`
                        : hoveredEdge
                        ? `Coupling ${hoveredEdge.id}`
                        : "Information"}
                    </h3>
                    <div className="divider my-2"></div>
                  </div>
                </div>

                <div className="space-y-4 pt-4">
                  {hoveredNode && (
                    <div className="overflow-x-auto">
                      <table className="table table-sm">
                        <tbody>
                          <tr>
                            <td className="font-medium">Status</td>
                            <td>{hoveredNode.data.status}</td>
                          </tr>
                          <tr>
                            <td className="font-medium">Calibrated</td>
                            <td>
                              {hoveredNode.data.isCalibrated ? "Yes" : "No"}
                            </td>
                          </tr>
                          {hoveredNode.data.qubitData && (
                            <>
                              {Object.entries(hoveredNode.data.qubitData).map(
                                ([key, value]) => (
                                  <tr key={key}>
                                    <td className="font-medium whitespace-normal">
                                      {key}
                                    </td>
                                    <td>
                                      {value.value} {value.unit || ""}
                                    </td>
                                  </tr>
                                )
                              )}
                            </>
                          )}
                        </tbody>
                      </table>
                    </div>
                  )}

                  {hoveredEdge && (
                    <div className="overflow-x-auto">
                      <table className="table table-sm">
                        <tbody>
                          <tr>
                            <td className="font-medium">Source</td>
                            <td>{hoveredEdge.source}</td>
                          </tr>
                          <tr>
                            <td className="font-medium">Target</td>
                            <td>{hoveredEdge.target}</td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  )}

                  {selectedQubit && !hoveredNode && !hoveredEdge && (
                    <CalibrationDetails qubit={selectedQubit} />
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
