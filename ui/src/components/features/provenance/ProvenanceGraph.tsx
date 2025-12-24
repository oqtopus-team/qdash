"use client";

import { useCallback, useMemo } from "react";
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

import type { LineageNodeResponse, LineageEdgeResponse } from "@/schemas";

interface ProvenanceGraphProps {
  nodes: LineageNodeResponse[];
  edges: LineageEdgeResponse[];
  originId?: string;
  onNodeClick?: (nodeId: string, nodeType: string) => void;
}

// Custom node for Entity (Parameter)
function EntityNode({ data }: { data: { label: string; value?: string; isOrigin?: boolean } }) {
  return (
    <div
      className={`px-4 py-3 rounded-lg border-2 shadow-md min-w-[150px] ${
        data.isOrigin
          ? "bg-primary/20 border-primary"
          : "bg-base-100 border-primary/50"
      }`}
    >
      <Handle type="target" position={Position.Top} className="!bg-primary" />
      <div className="text-sm font-medium text-center">{data.label}</div>
      {data.value && (
        <div className="text-xs text-base-content/70 text-center mt-1 font-mono">
          {data.value}
        </div>
      )}
      <Handle type="source" position={Position.Bottom} className="!bg-primary" />
    </div>
  );
}

// Custom node for Activity (Task)
function ActivityNode({ data }: { data: { label: string; status?: string } }) {
  return (
    <div className="px-4 py-3 rounded-lg border-2 border-secondary/50 bg-secondary/10 shadow-md min-w-[150px]">
      <Handle type="target" position={Position.Top} className="!bg-secondary" />
      <div className="text-sm font-medium text-center">{data.label}</div>
      {data.status && (
        <div className="text-xs text-base-content/70 text-center mt-1">
          {data.status}
        </div>
      )}
      <Handle type="source" position={Position.Bottom} className="!bg-secondary" />
    </div>
  );
}

const nodeTypes: NodeTypes = {
  entity: EntityNode,
  activity: ActivityNode,
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

// Convert API response to React Flow nodes and edges
function convertToFlowElements(
  apiNodes: LineageNodeResponse[],
  apiEdges: LineageEdgeResponse[],
  originId?: string
): { nodes: Node[]; edges: Edge[] } {
  // Calculate positions using a simple layered layout
  const nodePositions = new Map<string, { x: number; y: number }>();
  const nodesByDepth = new Map<number, string[]>();

  // Group nodes by depth (BFS from edges)
  const adjacencyList = new Map<string, string[]>();
  apiEdges.forEach((edge) => {
    if (!adjacencyList.has(edge.source_id)) {
      adjacencyList.set(edge.source_id, []);
    }
    adjacencyList.get(edge.source_id)!.push(edge.target_id);
  });

  // BFS to assign depths
  const depths = new Map<string, number>();
  if (originId) {
    depths.set(originId, 0);
    const queue = [originId];
    while (queue.length > 0) {
      const current = queue.shift()!;
      const currentDepth = depths.get(current)!;
      const neighbors = adjacencyList.get(current) || [];
      for (const neighbor of neighbors) {
        if (!depths.has(neighbor)) {
          depths.set(neighbor, currentDepth + 1);
          queue.push(neighbor);
        }
      }
    }
  }

  // Assign default depth to unvisited nodes
  apiNodes.forEach((node) => {
    if (!depths.has(node.node_id)) {
      depths.set(node.node_id, 0);
    }
    const depth = depths.get(node.node_id)!;
    if (!nodesByDepth.has(depth)) {
      nodesByDepth.set(depth, []);
    }
    nodesByDepth.get(depth)!.push(node.node_id);
  });

  // Calculate positions
  const horizontalSpacing = 250;
  const verticalSpacing = 120;

  nodesByDepth.forEach((nodeIds, depth) => {
    const totalWidth = (nodeIds.length - 1) * horizontalSpacing;
    const startX = -totalWidth / 2;

    nodeIds.forEach((nodeId, index) => {
      nodePositions.set(nodeId, {
        x: startX + index * horizontalSpacing,
        y: depth * verticalSpacing,
      });
    });
  });

  // Convert nodes
  const flowNodes: Node[] = apiNodes.map((node) => {
    const position = nodePositions.get(node.node_id) || { x: 0, y: 0 };
    const isEntity = node.node_type === "entity";

    let label = node.node_id.split(":").slice(0, 2).join(":");
    let value: string | undefined;
    let status: string | undefined;

    if (isEntity && node.entity) {
      label = `${node.entity.parameter_name || "?"}\n(${node.entity.qid || "?"})`;
      value = formatValue(node.entity.value);
    } else if (!isEntity && node.activity) {
      label = node.activity.task_name || node.node_id;
      status = node.activity.status;
    }

    return {
      id: node.node_id,
      type: isEntity ? "entity" : "activity",
      position,
      data: {
        label,
        value,
        status,
        isOrigin: node.node_id === originId,
      },
    };
  });

  // Convert edges
  const flowEdges: Edge[] = apiEdges.map((edge, index) => {
    // Determine edge style based on relation type
    let strokeColor = "#888";
    let label = "";

    switch (edge.relation_type) {
      case "wasGeneratedBy":
        strokeColor = "#22c55e"; // green
        label = "generated by";
        break;
      case "wasDerivedFrom":
        strokeColor = "#3b82f6"; // blue
        label = "derived from";
        break;
      case "used":
        strokeColor = "#f59e0b"; // amber
        label = "used";
        break;
    }

    return {
      id: `edge-${index}`,
      source: edge.source_id,
      target: edge.target_id,
      label,
      labelStyle: { fontSize: 10, fill: "#666" },
      labelBgStyle: { fill: "transparent" },
      style: { stroke: strokeColor, strokeWidth: 2 },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: strokeColor,
      },
      animated: edge.relation_type === "wasDerivedFrom",
    };
  });

  return { nodes: flowNodes, edges: flowEdges };
}

export function ProvenanceGraph({
  nodes: apiNodes,
  edges: apiEdges,
  originId,
  onNodeClick,
}: ProvenanceGraphProps) {
  const { nodes: initialNodes, edges: initialEdges } = useMemo(
    () => convertToFlowElements(apiNodes, apiEdges, originId),
    [apiNodes, apiEdges, originId]
  );

  const [nodes, , onNodesChange] = useNodesState(initialNodes);
  const [edges, , onEdgesChange] = useEdgesState(initialEdges);

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      if (onNodeClick) {
        const apiNode = apiNodes.find((n) => n.node_id === node.id);
        onNodeClick(node.id, apiNode?.node_type || "entity");
      }
    },
    [apiNodes, onNodeClick]
  );

  if (apiNodes.length === 0) {
    return (
      <div className="h-[400px] flex items-center justify-center text-base-content/50 bg-base-200 rounded-lg">
        No graph data available
      </div>
    );
  }

  return (
    <div className="h-[500px] bg-base-200 rounded-lg border border-base-300">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.1}
        maxZoom={2}
        defaultEdgeOptions={{
          type: "smoothstep",
        }}
      >
        <Background color="#666" gap={20} size={1} />
        <Controls />
        <MiniMap
          nodeColor={(node) =>
            node.type === "entity" ? "#3b82f6" : "#8b5cf6"
          }
          maskColor="rgba(0,0,0,0.2)"
        />
      </ReactFlow>

      {/* Legend */}
      <div className="absolute bottom-4 left-4 bg-base-100/90 p-3 rounded-lg shadow text-xs space-y-1">
        <div className="font-medium mb-2">Legend</div>
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 rounded border-2 border-primary bg-primary/20"></div>
          <span>Entity (Parameter)</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 rounded border-2 border-secondary bg-secondary/10"></div>
          <span>Activity (Task)</span>
        </div>
        <div className="flex items-center gap-2 mt-2">
          <div className="w-6 h-0.5 bg-green-500"></div>
          <span>wasGeneratedBy</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-6 h-0.5 bg-blue-500"></div>
          <span>wasDerivedFrom</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-6 h-0.5 bg-amber-500"></div>
          <span>used</span>
        </div>
      </div>
    </div>
  );
}
