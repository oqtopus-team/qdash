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
}: {
  chipData: ChipResponse;
  onNodeClick: (qubitId: string) => void;
}) => {
  if (!chipData.qubits || !chipData.couplings) return null;

  const [nodes, setNodes] = useState<QubitNode[]>([]);
  const [edges, setEdges] = useState<QubitEdge[]>([]);
  const [hoveredNode, setHoveredNode] = useState<QubitNode | null>(null);
  const [hoveredEdge, setHoveredEdge] = useState<QubitEdge | null>(null);

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
    setHoveredNode(node);
    setHoveredEdge(null);
  };

  const handleEdgePointerOver = (edge: any) => {
    setHoveredEdge(edge);
    setHoveredNode(null);
  };

  const handleNodeClick = (node: any) => {
    if (node) {
      onNodeClick(node.id);
    }
  };

  return (
    <div className="flex h-full">
      <div className="w-2/3" style={{ height: "400px" }}>
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
      <div className="w-1/3 p-4 bg-base-200 h-[400px] overflow-y-auto">
        <h3 className="text-lg font-bold mb-4 sticky top-0 bg-base-200">
          {hoveredNode
            ? `Qubit ${hoveredNode.id}`
            : hoveredEdge
            ? `Coupling ${hoveredEdge.id}`
            : "Select a qubit or coupling"}
        </h3>

        {hoveredNode && (
          <div className="space-y-2 overflow-y-auto">
            <p>Status: {hoveredNode.data.status}</p>
            <p>Calibrated: {hoveredNode.data.isCalibrated ? "Yes" : "No"}</p>
            {hoveredNode.data.qubitData &&
              Object.entries(hoveredNode.data.qubitData).map(([key, value]) => (
                <p key={key}>
                  {key}: {value.value} {value.unit || ""}
                </p>
              ))}
          </div>
        )}

        {hoveredEdge && (
          <div className="space-y-2 overflow-y-auto">
            <p>Source: {hoveredEdge.source}</p>
            <p>Target: {hoveredEdge.target}</p>
          </div>
        )}
      </div>
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

        <div className="grid grid-cols-3 gap-6 mt-6">
          <div className="col-span-2">
            {chipData?.data && (
              <div className="relative">
                <TopologyVisualization
                  chipData={chipData.data}
                  onNodeClick={(qubitId) => setSelectedQubitId(qubitId)}
                />
              </div>
            )}
          </div>
          <div className="col-span-1">
            <div className="card bg-base-100 shadow">
              <div className="card-body">
                <h2 className="card-title">
                  {selectedQubitId
                    ? `Qubit ${selectedQubitId} Calibration`
                    : "Select a qubit"}
                </h2>
                {selectedQubit && <CalibrationDetails qubit={selectedQubit} />}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
