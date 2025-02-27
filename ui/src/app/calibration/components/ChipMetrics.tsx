"use client";

import { useListChips, useFetchChip } from "@/client/chip/chip";
import { ChipResponse, NodeInfo, EdgeInfo } from "@/schemas";
import { useEffect, useState, useMemo } from "react";
import Select from "react-select";
import {
  ReactFlow,
  Background,
  Controls,
  Node,
  Edge,
  NodeProps,
  useNodesState,
  useEdgesState,
  OnNodesChange,
  OnEdgesChange,
  NodeMouseHandler,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

// SVG Topology component
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

// Custom node component for qubits
type QubitNodeData = {
  label: string;
  isCalibrated: boolean;
};

const QubitNode = ({
  data,
}: {
  data: QubitNodeData & Record<string, unknown>;
}) => {
  return (
    <div
      className="flex items-center justify-center w-8 h-8 rounded-full border-2"
      style={{
        backgroundColor: data.isCalibrated ? "#4CAF50" : "#ccc",
        borderColor: "#333",
      }}
    >
      <span className="text-xs text-black">{data.label}</span>
    </div>
  );
};

const TopologyVisualization = ({
  chipData,
  onNodeClick,
}: {
  chipData: ChipResponse;
  onNodeClick: (qubitId: string) => void;
}) => {
  if (!chipData.qubits || !chipData.couplings) return null;

  // Convert qubits to nodes
  const initialNodes: Node<QubitNodeData>[] = Object.entries(
    chipData.qubits as Record<string, QubitData>
  ).map(([id, qubit]) => ({
    id,
    type: "qubit",
    position: qubit.node_info.position,
    data: {
      label: id,
      isCalibrated: qubit.data && Object.keys(qubit.data).length > 0,
    },
  }));

  // Convert couplings to edges
  const initialEdges: Edge[] = Object.entries(
    chipData.couplings as Record<string, CouplingData>
  ).map(([id, coupling]) => ({
    id,
    source: coupling.edge_info.source,
    target: coupling.edge_info.target,
    style: { stroke: "#666", strokeWidth: coupling.edge_info.size || 2 },
  }));

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  const nodeTypes = useMemo(() => {
    return {
      qubit: QubitNode as unknown as React.ComponentType<NodeProps>,
    };
  }, []);

  return (
    <div style={{ width: "100%", height: "400px" }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        onNodeClick={(_: React.MouseEvent, node: Node<QubitNodeData>) =>
          onNodeClick(node.id)
        }
        fitView
      >
        <Background />
        <Controls />
      </ReactFlow>
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
