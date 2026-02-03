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
  type NodeProps,
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
function EntityNode({ data, selected }: NodeProps) {
  const typedData = data as {
    label: string;
    value?: string;
    isOrigin?: boolean;
    unit?: string;
    qid?: string;
    error?: string;
    lowConfidence?: boolean;
    isMatch?: boolean;
    dimmed?: boolean;
  };
  const styles = getNodeStyles(typedData.isOrigin ?? false, true);

  return (
    <div
      className={`px-4 py-3 shadow-lg rounded-lg border-2 min-w-[160px] max-w-[200px] ${
        selected || typedData.isMatch ? "ring-2 ring-accent" : ""
      } ${typedData.lowConfidence ? "border-warning" : ""}`}
      style={{
        backgroundColor: styles.background,
        borderColor: styles.borderColor,
        opacity: typedData.dimmed ? 0.25 : 1,
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
              typedData.isOrigin ? "bg-primary" : "bg-primary/50"
            }`}
          />
          <div className="font-semibold text-sm truncate">
            {typedData.label}
          </div>
        </div>
        {typedData.qid && (
          <span className="badge badge-primary badge-sm flex-shrink-0">
            {typedData.qid}
          </span>
        )}
      </div>
      {typedData.value && (
        <div className="text-xs text-base-content/70 font-mono mt-1 bg-base-100/50 rounded px-2 py-1 text-center">
          {typedData.value} {typedData.unit || ""}
        </div>
      )}
      {typedData.error && (
        <div
          className={`text-[10px] font-mono mt-1 rounded px-2 py-1 text-center ${
            typedData.lowConfidence
              ? "bg-warning/10 text-warning"
              : "bg-base-100/50 text-base-content/60"
          }`}
          title="Measurement uncertainty (error)"
        >
          ±{typedData.error}
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
function ActivityNode({ data, selected }: NodeProps) {
  const typedData = data as {
    label: string;
    status?: string;
    taskId?: string;
    qid?: string;
    isMatch?: boolean;
    dimmed?: boolean;
    isPinned?: boolean;
  };
  const styles = getNodeStyles(false, false);

  const statusClass =
    typedData.status === "completed"
      ? "text-success"
      : typedData.status === "failed"
        ? "text-error"
        : typedData.status === "running"
          ? "text-info"
          : "text-warning";

  return (
    <div
      className={`px-4 py-3 shadow-lg rounded-lg border-2 min-w-[160px] max-w-[200px] cursor-pointer ${
        selected || typedData.isMatch ? "ring-2 ring-accent" : ""
      } ${typedData.isPinned ? "ring-2 ring-secondary" : ""}`}
      style={{
        backgroundColor: styles.background,
        borderColor: styles.borderColor,
        opacity: typedData.dimmed ? 0.25 : 1,
      }}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!bg-secondary !w-2 !h-2"
      />
      <div className="flex items-center gap-2">
        <div className="w-2 h-2 rounded-sm bg-secondary/60 flex-shrink-0" />
        <div className="font-semibold text-sm truncate">{typedData.label}</div>
      </div>
      {typedData.status && (
        <div className={`text-xs ${statusClass} mt-1 capitalize`}>
          {typedData.status}
        </div>
      )}
      {typedData.taskId && (
        <div className="text-[10px] text-base-content/50 mt-1 truncate">
          Click to pin preview
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

function normalizeForSearch(value: unknown): string {
  return String(value ?? "")
    .toLowerCase()
    .trim();
}

function nodeMatchesQuery(node: LineageNodeResponse, query: string): boolean {
  const q = normalizeForSearch(query);
  if (!q) return false;

  const parts: string[] = [node.node_id, node.node_type];
  if (node.node_type === "entity" && node.entity) {
    parts.push(
      node.entity.parameter_name ?? "",
      node.entity.qid ?? "",
      node.entity.unit ?? "",
      String(node.entity.value ?? ""),
    );
  }
  if (node.node_type === "activity" && node.activity) {
    parts.push(
      node.activity.task_name ?? "",
      node.activity.status ?? "",
      node.activity.task_id ?? "",
      node.activity.qid ?? "",
    );
  }

  return normalizeForSearch(parts.join(" ")).includes(q);
}

function buildUndirectedAdjacency(edges: LineageEdgeResponse[]) {
  const adjacency = new Map<string, Set<string>>();
  const add = (from: string, to: string) => {
    if (!adjacency.has(from)) adjacency.set(from, new Set());
    adjacency.get(from)!.add(to);
  };
  for (const edge of edges) {
    add(edge.source_id, edge.target_id);
    add(edge.target_id, edge.source_id);
  }
  return adjacency;
}

function computeHopDistances(
  originId: string,
  edges: LineageEdgeResponse[],
): Map<string, number> {
  const adjacency = buildUndirectedAdjacency(edges);
  const distance = new Map<string, number>();
  const queue: string[] = [];
  distance.set(originId, 0);
  queue.push(originId);

  while (queue.length > 0) {
    const current = queue.shift()!;
    const d = distance.get(current) ?? 0;
    const neighbors = adjacency.get(current);
    if (!neighbors) continue;
    for (const next of neighbors) {
      if (!distance.has(next)) {
        distance.set(next, d + 1);
        queue.push(next);
      }
    }
  }

  return distance;
}

// Helper to format value for display
function formatValue(value: unknown): string {
  if (value === undefined || value === null) return "";
  if (typeof value === "number") {
    if (Math.abs(value) < 0.01 || Math.abs(value) > 10000) {
      return value.toExponential(2);
    }
    return value.toFixed(4);
  }
  if (typeof value === "boolean") return value ? "true" : "false";
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
    let error: string | undefined;
    let lowConfidence: boolean | undefined;
    let status: string | undefined;
    let unit: string | undefined;
    let taskId: string | undefined;
    let qid: string | undefined;

    if (isEntity && node.entity) {
      label = node.entity.parameter_name || "?";
      value = formatValue(node.entity.value);
      unit = node.entity.unit;
      qid = node.entity.qid;
      if (typeof node.entity.error === "number" && node.entity.error !== 0) {
        error = formatValue(node.entity.error);
        if (typeof node.entity.value === "number") {
          if (node.entity.value === 0) {
            lowConfidence = true;
          } else {
            lowConfidence =
              Math.abs(node.entity.error / node.entity.value) >= 0.05;
          }
        }
      }
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
        error,
        lowConfidence,
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
  const [pinnedTask, setPinnedTask] = useState<{
    taskId: string;
    qid: string;
    taskName?: string;
  } | null>(null);
  const [showDerivedEdges, setShowDerivedEdges] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [focusHops, setFocusHops] = useState(4);
  const [showAll, setShowAll] = useState(false);

  // Filter out wasDerivedFrom edges when toggle is off
  const filteredApiEdges = useMemo(() => {
    if (showDerivedEdges) return apiEdges;
    return apiEdges.filter((edge) => edge.relation_type !== "wasDerivedFrom");
  }, [apiEdges, showDerivedEdges]);

  const matchingNodeIds = useMemo(() => {
    if (!searchQuery) return new Set<string>();
    return new Set(
      apiNodes
        .filter((n) => nodeMatchesQuery(n, searchQuery))
        .map((n) => n.node_id),
    );
  }, [apiNodes, searchQuery]);

  const hopDistances = useMemo(() => {
    if (!originId) return new Map<string, number>();
    return computeHopDistances(originId, filteredApiEdges);
  }, [originId, filteredApiEdges]);

  const maxDistance = useMemo(() => {
    let max = 0;
    for (const d of hopDistances.values()) max = Math.max(max, d);
    return max;
  }, [hopDistances]);

  useEffect(() => {
    if (focusHops > maxDistance && maxDistance > 0) {
      setFocusHops(maxDistance);
    }
  }, [focusHops, maxDistance]);

  const effectiveShowAll =
    showAll || (!!searchQuery && matchingNodeIds.size > 0);
  const maxHopsToShow = effectiveShowAll ? Number.POSITIVE_INFINITY : focusHops;

  const constrainedApiNodes = useMemo(() => {
    if (!originId) return apiNodes;
    return apiNodes.filter(
      (n) => (hopDistances.get(n.node_id) ?? Infinity) <= maxHopsToShow,
    );
  }, [apiNodes, hopDistances, maxHopsToShow, originId]);

  const constrainedNodeIds = useMemo(
    () => new Set(constrainedApiNodes.map((n) => n.node_id)),
    [constrainedApiNodes],
  );

  const constrainedApiEdges = useMemo(() => {
    return filteredApiEdges.filter(
      (e) =>
        constrainedNodeIds.has(e.source_id) &&
        constrainedNodeIds.has(e.target_id),
    );
  }, [filteredApiEdges, constrainedNodeIds]);

  const { nodes: baseNodes, edges: baseEdges } = useMemo(
    () =>
      convertToFlowElements(constrainedApiNodes, constrainedApiEdges, originId),
    [constrainedApiNodes, constrainedApiEdges, originId],
  );

  const { nodes: initialNodes, edges: initialEdges } = useMemo(() => {
    const hasSearch = !!searchQuery && matchingNodeIds.size > 0;
    const matchNeighborhood = (() => {
      if (!hasSearch) return new Set<string>();
      const neighbors = new Set<string>(matchingNodeIds);
      for (const edge of baseEdges) {
        if (
          matchingNodeIds.has(edge.source) ||
          matchingNodeIds.has(edge.target)
        ) {
          neighbors.add(edge.source);
          neighbors.add(edge.target);
        }
      }
      return neighbors;
    })();

    const withDecorations = baseNodes.map((node) => {
      const isMatch = matchingNodeIds.has(node.id);
      const dimmed = hasSearch ? !matchNeighborhood.has(node.id) : false;
      const isPinned =
        node.type === "activity" &&
        !!pinnedTask?.taskId &&
        (node.data as any)?.taskId === pinnedTask.taskId;
      return {
        ...node,
        data: { ...(node.data as any), isMatch, dimmed, isPinned },
      };
    });

    const withEdgeDimming = baseEdges.map((edge) => {
      const dimmed =
        !!searchQuery &&
        matchingNodeIds.size > 0 &&
        !(
          matchNeighborhood.has(edge.source) ||
          matchNeighborhood.has(edge.target)
        );
      return {
        ...edge,
        style: { ...(edge.style as any), opacity: dimmed ? 0.15 : 1 },
      };
    });

    return { nodes: withDecorations, edges: withEdgeDimming };
  }, [baseNodes, baseEdges, matchingNodeIds, searchQuery, pinnedTask?.taskId]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Update nodes and edges when data changes (e.g., toggle derived edges)
  useEffect(() => {
    setNodes(initialNodes);
    setEdges(initialEdges);
  }, [initialNodes, initialEdges, setNodes, setEdges]);

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      const apiNode = apiNodes.find((n) => n.node_id === node.id);
      if (apiNode?.node_type === "activity" && (node.data as any)?.taskId) {
        const taskId = (node.data as any).taskId as string;
        const qid = ((node.data as any).qid as string) || "0";
        const taskName =
          typeof (node.data as any).label === "string"
            ? ((node.data as any).label as string)
            : undefined;
        setPinnedTask((prev) => {
          if (prev?.taskId === taskId && prev?.qid === qid) return null;
          return { taskId, qid, taskName };
        });
        return;
      }

      if (onNodeClick) {
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

  const visibleCounts = useMemo(() => {
    const entityCount = initialNodes.filter((n) => n.type === "entity").length;
    const taskCount = initialNodes.filter((n) => n.type === "activity").length;
    const failedTasks = initialNodes.filter(
      (n) => n.type === "activity" && (n.data as any)?.status === "failed",
    ).length;
    const lowConfidenceParams = initialNodes.filter(
      (n) => n.type === "entity" && (n.data as any)?.lowConfidence,
    ).length;
    return { entityCount, taskCount, failedTasks, lowConfidenceParams };
  }, [initialNodes]);

  if (apiNodes.length === 0) {
    return (
      <div className="h-[calc(100vh-16rem)] min-h-[500px] flex flex-col items-center justify-center text-base-content/50 bg-base-200 rounded-lg border border-base-300">
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

  const taskToShow = pinnedTask ?? hoveredTask;

  return (
    <div className="h-[calc(100vh-16rem)] min-h-[500px] bg-base-200 rounded-lg border border-base-300 overflow-hidden relative">
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

      {/* Controls / Summary */}
      <div className="absolute top-4 left-4 right-4 flex flex-col sm:flex-row gap-2 items-start sm:items-center z-20 pointer-events-none">
        <div className="flex items-center gap-2 bg-base-100/90 border border-base-300 rounded-lg px-3 py-2 shadow-sm w-full sm:w-auto">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Find parameter/task..."
            className="input input-bordered input-sm w-full sm:w-56 pointer-events-auto"
          />
          {searchQuery && (
            <button
              className="btn btn-ghost btn-sm pointer-events-auto"
              onClick={() => setSearchQuery("")}
            >
              Clear
            </button>
          )}
        </div>

        <div className="flex items-center gap-2 bg-base-100/90 border border-base-300 rounded-lg px-3 py-2 shadow-sm w-full sm:w-auto">
          <div className="text-xs text-base-content/60 whitespace-nowrap">
            Focus
          </div>
          <input
            type="range"
            min={1}
            max={Math.max(1, Math.min(10, maxDistance || 10))}
            value={Math.min(
              focusHops,
              Math.max(1, Math.min(10, maxDistance || 10)),
            )}
            onChange={(e) => setFocusHops(Number(e.target.value))}
            className="range range-xs range-primary w-28 pointer-events-auto"
            disabled={effectiveShowAll}
          />
          <div className="text-xs font-medium tabular-nums w-10 text-right">
            {effectiveShowAll ? "All" : `${focusHops}h`}
          </div>
          <button
            className={`btn btn-xs pointer-events-auto ${effectiveShowAll ? "btn-active" : ""}`}
            onClick={() => setShowAll((v) => !v)}
          >
            All
          </button>
          <div className="flex items-center gap-2 ml-2">
            <input
              type="checkbox"
              className="checkbox checkbox-xs checkbox-primary pointer-events-auto"
              checked={showDerivedEdges}
              onChange={(e) => setShowDerivedEdges(e.target.checked)}
              id="show-derived"
            />
            <label
              htmlFor="show-derived"
              className="text-xs text-base-content/60 cursor-pointer pointer-events-auto"
            >
              derived
            </label>
          </div>
        </div>

        <div className="flex items-center gap-2 bg-base-100/90 border border-base-300 rounded-lg px-3 py-2 shadow-sm ml-0 sm:ml-auto w-full sm:w-auto">
          <span className="badge badge-primary badge-sm">
            {initialNodes.length}/{apiNodes.length} shown
          </span>
          <span className="badge badge-ghost badge-sm">
            params {visibleCounts.entityCount}
          </span>
          <span className="badge badge-ghost badge-sm">
            tasks {visibleCounts.taskCount}
          </span>
          {visibleCounts.failedTasks > 0 && (
            <span className="badge badge-error badge-sm">
              failed {visibleCounts.failedTasks}
            </span>
          )}
          {visibleCounts.lowConfidenceParams > 0 && (
            <span className="badge badge-warning badge-sm">
              uncertain {visibleCounts.lowConfidenceParams}
            </span>
          )}
        </div>
      </div>

      {/* Task Result Preview Panel */}
      {taskToShow && (
        <div className="absolute top-20 right-4 w-80 bg-base-100 rounded-lg shadow-xl border border-base-300 overflow-hidden z-10">
          <div className="bg-secondary/10 px-4 py-2 border-b border-base-300">
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="text-sm font-medium truncate">
                  {pinnedTask ? "Pinned Task Preview" : "Task Result Preview"}
                </div>
                {pinnedTask?.taskName && (
                  <div className="text-xs text-base-content/60 truncate">
                    {pinnedTask.taskName}
                  </div>
                )}
              </div>
              {pinnedTask && (
                <button
                  className="btn btn-ghost btn-xs"
                  onClick={() => setPinnedTask(null)}
                >
                  Close
                </button>
              )}
            </div>
            <div className="text-xs text-base-content/60">
              Qubit: {taskToShow.qid}
            </div>
          </div>
          <div className="p-2 max-h-[300px] overflow-auto">
            <TaskFigure
              taskId={taskToShow.taskId}
              qid={taskToShow.qid}
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
        <div className="flex items-center gap-1.5 mt-2 pt-2 border-t border-base-300">
          <div className="w-4 h-0.5 bg-blue-500 rounded" />
          <span className="text-base-content/60">derived</span>
        </div>
      </div>
    </div>
  );
}
