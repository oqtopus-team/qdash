"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type NodeTypes,
  Handle,
  Position,
  MarkerType,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import dagre from "dagre";

import { TaskFigure } from "@/components/charts/TaskFigure";
import { FluentEmoji } from "@/components/ui/FluentEmoji";
import type { LineageNodeResponse, LineageEdgeResponse } from "@/schemas";

interface ProvenanceGraphProps {
  nodes: LineageNodeResponse[];
  edges: LineageEdgeResponse[];
  originId?: string;
  onNodeClick?: (nodeId: string, nodeType: string) => void;
}

// Status-based styling following ExecutionDAG pattern
const getNodeStyles = (isOrigin: boolean, isEntity: boolean) => {
  if (isOrigin) {
    return {
      background: "hsl(var(--p) / 0.15)",
      borderColor: "hsl(var(--p))",
    };
  }
  if (isEntity) {
    return {
      background: "hsl(var(--b2))",
      borderColor: "hsl(var(--p) / 0.4)",
    };
  }
  return {
    background: "hsl(var(--b2))",
    borderColor: "hsl(var(--s) / 0.4)",
  };
};

// Custom node for Entity (Parameter)
function EntityNode({
  data,
}: {
  data: {
    label: string;
    value?: string;
    isOrigin?: boolean;
    unit?: string;
    qid?: string;
  };
}) {
  const styles = getNodeStyles(data.isOrigin ?? false, true);

  return (
    <div
      className="px-4 py-3 shadow-lg rounded-lg border-2 min-w-[160px] max-w-[200px]"
      style={{
        backgroundColor: styles.background,
        borderColor: styles.borderColor,
      }}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!bg-primary !w-2 !h-2"
      />
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <div
            className={`w-2 h-2 rounded-full flex-shrink-0 ${
              data.isOrigin ? "bg-primary" : "bg-primary/50"
            }`}
          />
          <div className="font-semibold text-sm truncate">{data.label}</div>
        </div>
        {data.qid && (
          <span className="badge badge-primary badge-sm flex-shrink-0">
            {data.qid}
          </span>
        )}
      </div>
      {data.value && (
        <div className="text-xs text-base-content/70 font-mono mt-1 bg-base-100/50 rounded px-2 py-1 text-center">
          {data.value} {data.unit || ""}
        </div>
      )}
      <Handle
        type="source"
        position={Position.Bottom}
        className="!bg-primary !w-2 !h-2"
      />
    </div>
  );
}

// Custom node for Activity (Task) with hover capability
function ActivityNode({
  data,
}: {
  data: {
    label: string;
    status?: string;
    taskId?: string;
    qid?: string;
  };
}) {
  const styles = getNodeStyles(false, false);

  const statusClass =
    data.status === "completed"
      ? "text-success"
      : data.status === "failed"
        ? "text-error"
        : data.status === "running"
          ? "text-info"
          : "text-warning";

  return (
    <div
      className="px-4 py-3 shadow-lg rounded-lg border-2 min-w-[160px] max-w-[200px] cursor-pointer"
      style={{
        backgroundColor: styles.background,
        borderColor: styles.borderColor,
      }}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!bg-secondary !w-2 !h-2"
      />
      <div className="flex items-center gap-2">
        <div className="w-2 h-2 rounded-sm bg-secondary/60 flex-shrink-0" />
        <div className="font-semibold text-sm truncate">{data.label}</div>
      </div>
      {data.status && (
        <div className={`text-xs ${statusClass} mt-1 capitalize`}>
          {data.status}
        </div>
      )}
      {data.taskId && (
        <div className="text-[10px] text-base-content/50 mt-1 truncate">
          Hover for result
        </div>
      )}
      <Handle
        type="source"
        position={Position.Bottom}
        className="!bg-secondary !w-2 !h-2"
      />
    </div>
  );
}

const nodeTypes: NodeTypes = {
  entity: EntityNode,
  activity: ActivityNode,
};

// Edge colors by relation type
const EDGE_COLORS = {
  wasGeneratedBy: "#22c55e", // green-500
  wasDerivedFrom: "#3b82f6", // blue-500
  used: "#f59e0b", // amber-500
  default: "#64748b", // slate-500
};

// Helper to format value for display
function formatValue(value: number | string | undefined): string {
  if (value === undefined || value === null) return "";
  if (typeof value === "number") {
    if (Math.abs(value) < 0.01 || Math.abs(value) > 10000) {
      return value.toExponential(2);
    }
    return value.toFixed(4);
  }
  return String(value);
}

// Use dagre for automatic hierarchical layout
function getLayoutedElements(
  nodes: Node[],
  edges: Edge[],
  direction: "TB" | "BT" | "LR" | "RL" = "TB",
): { nodes: Node[]; edges: Edge[] } {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));

  const isHorizontal = direction === "LR" || direction === "RL";
  dagreGraph.setGraph({
    rankdir: direction,
    nodesep: 60,
    ranksep: 80,
    marginx: 40,
    marginy: 40,
  });

  // Add nodes to dagre
  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: 180, height: 70 });
  });

  // Add edges to dagre
  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  // Calculate layout
  dagre.layout(dagreGraph);

  // Apply positions to nodes
  const layoutedNodes = nodes.map((node) => {
    const dagreNode = dagreGraph.node(node.id);
    return {
      ...node,
      position: {
        x: dagreNode.x - 90,
        y: dagreNode.y - 35,
      },
      targetPosition: isHorizontal ? Position.Left : Position.Top,
      sourcePosition: isHorizontal ? Position.Right : Position.Bottom,
    };
  });

  return { nodes: layoutedNodes, edges };
}

// Convert API response to React Flow nodes and edges
function convertToFlowElements(
  apiNodes: LineageNodeResponse[],
  apiEdges: LineageEdgeResponse[],
  originId?: string,
): { nodes: Node[]; edges: Edge[] } {
  // Convert nodes
  const flowNodes: Node[] = apiNodes.map((node) => {
    const isEntity = node.node_type === "entity";

    let label = node.node_id.split(":").slice(0, 2).join(":");
    let value: string | undefined;
    let status: string | undefined;
    let unit: string | undefined;
    let taskId: string | undefined;
    let qid: string | undefined;

    if (isEntity && node.entity) {
      label = node.entity.parameter_name || "?";
      value = formatValue(node.entity.value);
      unit = node.entity.unit;
      qid = node.entity.qid;
    } else if (!isEntity && node.activity) {
      label = node.activity.task_name || node.node_id;
      status = node.activity.status;
      taskId = node.activity.task_id;
      qid = node.activity.qid;
    }

    return {
      id: node.node_id,
      type: isEntity ? "entity" : "activity",
      position: { x: 0, y: 0 },
      data: {
        label,
        value,
        unit,
        status,
        taskId,
        qid,
        isOrigin: node.node_id === originId,
      },
    };
  });

  // Convert edges
  const flowEdges: Edge[] = apiEdges.map((edge, index) => {
    const strokeColor =
      EDGE_COLORS[edge.relation_type as keyof typeof EDGE_COLORS] ||
      EDGE_COLORS.default;

    return {
      id: `edge-${index}`,
      source: edge.source_id,
      target: edge.target_id,
      type: "smoothstep",
      style: { stroke: strokeColor, strokeWidth: 2 },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: strokeColor,
        width: 16,
        height: 16,
      },
      animated: edge.relation_type === "wasDerivedFrom",
    };
  });

  // Apply dagre layout
  return getLayoutedElements(flowNodes, flowEdges, "TB");
}

export function ProvenanceGraph({
  nodes: apiNodes,
  edges: apiEdges,
  originId,
  onNodeClick,
}: ProvenanceGraphProps) {
  const [hoveredTask, setHoveredTask] = useState<{
    taskId: string;
    qid: string;
  } | null>(null);
  const [showDerivedEdges, setShowDerivedEdges] = useState(false);

  // Filter out wasDerivedFrom edges when toggle is off
  const filteredApiEdges = useMemo(() => {
    if (showDerivedEdges) return apiEdges;
    return apiEdges.filter((edge) => edge.relation_type !== "wasDerivedFrom");
  }, [apiEdges, showDerivedEdges]);

  const { nodes: initialNodes, edges: initialEdges } = useMemo(
    () => convertToFlowElements(apiNodes, filteredApiEdges, originId),
    [apiNodes, filteredApiEdges, originId],
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Update nodes and edges when data changes (e.g., toggle derived edges)
  useEffect(() => {
    setNodes(initialNodes);
    setEdges(initialEdges);
  }, [initialNodes, initialEdges, setNodes, setEdges]);

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      if (onNodeClick) {
        const apiNode = apiNodes.find((n) => n.node_id === node.id);
        onNodeClick(node.id, apiNode?.node_type || "entity");
      }
    },
    [apiNodes, onNodeClick],
  );

  const handleNodeMouseEnter = useCallback(
    (_: React.MouseEvent, node: Node) => {
      if (node.type === "activity" && node.data.taskId) {
        setHoveredTask({
          taskId: node.data.taskId as string,
          qid: (node.data.qid as string) || "0",
        });
      }
    },
    [],
  );

  const handleNodeMouseLeave = useCallback(() => {
    setHoveredTask(null);
  }, []);

  if (apiNodes.length === 0) {
    return (
      <div className="h-[500px] flex flex-col items-center justify-center text-base-content/50 bg-base-200 rounded-lg border border-base-300">
        <div className="mb-4">
          <FluentEmoji name="empty" size={64} />
        </div>
        <p className="text-lg font-medium">No lineage data</p>
        <p className="text-sm mt-1">
          Select a parameter to explore its provenance
        </p>
      </div>
    );
  }

  return (
    <div className="h-[600px] bg-base-200 rounded-lg border border-base-300 overflow-hidden relative">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        onNodeMouseEnter={handleNodeMouseEnter}
        onNodeMouseLeave={handleNodeMouseLeave}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        minZoom={0.1}
        maxZoom={2}
        defaultEdgeOptions={{
          type: "smoothstep",
        }}
        proOptions={{ hideAttribution: true }}
      >
        <Background
          color="currentColor"
          className="text-base-content/10"
          gap={20}
          size={1}
        />
        <Controls
          className="!bg-base-100 !border-base-300 !rounded-lg !shadow"
          showInteractive={false}
        />
        <MiniMap
          nodeColor={(node) =>
            node.type === "entity" ? "oklch(var(--p))" : "oklch(var(--s))"
          }
          maskColor="rgba(0,0,0,0.1)"
          className="!bg-base-100/80 !border-base-300 !rounded-lg"
          pannable
          zoomable
        />
      </ReactFlow>

      {/* Task Result Preview Panel */}
      {hoveredTask && (
        <div className="absolute top-4 right-4 w-80 bg-base-100 rounded-lg shadow-xl border border-base-300 overflow-hidden z-10">
          <div className="bg-secondary/10 px-4 py-2 border-b border-base-300">
            <div className="text-sm font-medium">Task Result Preview</div>
            <div className="text-xs text-base-content/60">
              Qubit: {hoveredTask.qid}
            </div>
          </div>
          <div className="p-2 max-h-[300px] overflow-auto">
            <TaskFigure
              taskId={hoveredTask.taskId}
              qid={hoveredTask.qid}
              className="w-full h-auto rounded"
            />
          </div>
        </div>
      )}

      {/* Legend */}
      <div className="absolute bottom-4 left-4 bg-base-100 p-3 rounded-lg shadow border border-base-300 text-xs">
        <div className="font-medium mb-2">Legend</div>
        <div className="flex gap-4">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded bg-primary/20 border border-primary/50" />
            <span className="text-base-content/70">Parameter</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded bg-secondary/20 border border-secondary/50" />
            <span className="text-base-content/70">Task</span>
          </div>
        </div>
        <div className="flex gap-4 mt-2 pt-2 border-t border-base-300">
          <div className="flex items-center gap-1.5">
            <div className="w-4 h-0.5 bg-green-500 rounded" />
            <span className="text-base-content/60">generated</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-4 h-0.5 bg-amber-500 rounded" />
            <span className="text-base-content/60">used</span>
          </div>
        </div>
        {/* Derived edges toggle */}
        <div className="flex items-center gap-2 mt-2 pt-2 border-t border-base-300">
          <input
            type="checkbox"
            className="checkbox checkbox-xs checkbox-primary"
            checked={showDerivedEdges}
            onChange={(e) => setShowDerivedEdges(e.target.checked)}
            id="show-derived"
          />
          <label
            htmlFor="show-derived"
            className="flex items-center gap-1.5 cursor-pointer"
          >
            <div className="w-4 h-0.5 bg-blue-500 rounded" />
            <span className="text-base-content/60">derived</span>
          </label>
        </div>
      </div>

      {/* Hint */}
      <div className="absolute top-4 left-4 bg-base-100 px-3 py-1.5 rounded text-xs text-base-content/60 border border-base-300">
        Hover on tasks to preview results
      </div>
    </div>
  );
}
