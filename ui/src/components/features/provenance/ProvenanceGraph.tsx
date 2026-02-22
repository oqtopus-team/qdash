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

import { FluentEmoji } from "@/components/ui/FluentEmoji";
import type { LineageNodeResponse, LineageEdgeResponse } from "@/schemas";
import { TaskDetailPanel } from "./TaskDetailPanel";

interface ProvenanceGraphProps {
  nodes: LineageNodeResponse[];
  edges: LineageEdgeResponse[];
  originId?: string;
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
    latestVersion?: number;
    hasNewerVersion?: boolean;
    nodeVersion?: number;
  };
  const styles = getNodeStyles(typedData.isOrigin ?? false, true);

  // Compact value + unit + error in one line
  const valueParts: string[] = [];
  if (typedData.value)
    valueParts.push(
      `${typedData.value}${typedData.unit ? ` ${typedData.unit}` : ""}`,
    );
  if (typedData.error) valueParts.push(`±${typedData.error}`);
  const valueText = valueParts.join("  ");

  return (
    <div
      className={`group/entity px-3 py-2 shadow-md rounded-full border-2 min-w-[180px] max-w-[240px] relative ${
        selected || typedData.isMatch ? "ring-2 ring-accent" : ""
      } ${typedData.lowConfidence ? "border-warning" : ""} ${typedData.hasNewerVersion ? "border-info" : ""}`}
      style={{
        backgroundColor: styles.background,
        borderColor: typedData.hasNewerVersion
          ? "hsl(var(--in))"
          : styles.borderColor,
        opacity: typedData.dimmed ? 0.25 : 1,
      }}
    >
      {typedData.hasNewerVersion && (
        <>
          <span className="absolute -top-1 -right-1 flex h-3 w-3">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-info opacity-75" />
            <span className="relative inline-flex rounded-full h-3 w-3 bg-info" />
          </span>
          {/* Hover tooltip - stale */}
          <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-base-100 border border-info/30 text-base-content text-xs rounded-lg shadow-lg opacity-0 group-hover/entity:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-50">
            <div className="font-semibold text-info mb-1">
              Input version updated
            </div>
            <div>
              <span className="font-mono">v{typedData.nodeVersion}</span>
              <span className="mx-1">&rarr;</span>
              <span className="font-mono font-semibold">
                v{typedData.latestVersion}
              </span>
            </div>
            <div className="text-base-content/60 mt-1">
              Recalibration recommended
            </div>
            <div className="absolute top-full left-1/2 -translate-x-1/2 w-0 h-0 border-l-[6px] border-r-[6px] border-t-[6px] border-l-transparent border-r-transparent border-t-base-100" />
          </div>
        </>
      )}
      <Handle
        type="target"
        position={Position.Top}
        className="!bg-primary !w-2 !h-2"
      />
      {/* Row 1: name + qid */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 min-w-0">
          <div
            className={`w-2 h-2 rounded-full flex-shrink-0 ${
              typedData.isOrigin ? "bg-primary" : "bg-primary/40"
            }`}
          />
          <div className="font-semibold text-xs truncate">
            {typedData.label}
          </div>
        </div>
        {typedData.qid && (
          <span className="text-[10px] text-primary/70 font-mono flex-shrink-0">
            {typedData.qid}
          </span>
        )}
      </div>
      {/* Row 2: value ± error (single line) */}
      {valueText && (
        <div
          className={`text-[10px] font-mono mt-0.5 text-center truncate ${
            typedData.lowConfidence ? "text-warning" : "text-base-content/60"
          }`}
        >
          {valueText}
        </div>
      )}
      {/* Row 3: version update badge */}
      {typedData.hasNewerVersion &&
        typedData.nodeVersion != null &&
        typedData.latestVersion != null && (
          <div className="text-[9px] font-mono mt-0.5 rounded-full px-2 py-0.5 text-center bg-info/10 text-info">
            v{typedData.nodeVersion} &rarr; v{typedData.latestVersion}
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
    isTaskFlow?: boolean;
    staleInputCount?: number;
    staleInputNames?: string[];
  };
  const styles = getNodeStyles(false, false);
  const hasStaleInputs = (typedData.staleInputCount ?? 0) > 0;

  const statusClass =
    typedData.status === "completed"
      ? "text-success"
      : typedData.status === "failed"
        ? "text-error"
        : typedData.status === "running"
          ? "text-info"
          : "text-warning";

  const sizeClass = typedData.isTaskFlow
    ? "px-5 py-4 min-w-[240px] max-w-[280px] rounded-lg"
    : "px-4 py-2.5 min-w-[200px] max-w-[260px] rounded-xl";

  return (
    <div
      className={`group/activity ${sizeClass} shadow-lg border-2 cursor-pointer relative ${
        selected || typedData.isMatch ? "ring-2 ring-accent" : ""
      } ${typedData.isPinned ? "ring-2 ring-secondary" : ""}`}
      style={{
        backgroundColor: styles.background,
        borderColor: hasStaleInputs ? "hsl(var(--in))" : styles.borderColor,
        opacity: typedData.dimmed ? 0.25 : 1,
      }}
    >
      {hasStaleInputs && (
        <>
          <span className="absolute -top-1.5 -right-1.5 flex h-3.5 w-3.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-info opacity-75" />
            <span className="relative inline-flex rounded-full h-3.5 w-3.5 bg-info" />
          </span>
          {/* Hover tooltip */}
          <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-base-100 border border-info/30 text-base-content text-xs rounded-lg shadow-lg opacity-0 group-hover/activity:opacity-100 transition-opacity pointer-events-none z-50 min-w-[180px]">
            <div className="font-semibold text-info mb-1">
              Stale inputs detected
            </div>
            {typedData.staleInputNames &&
            typedData.staleInputNames.length > 0 ? (
              <ul className="space-y-0.5">
                {typedData.staleInputNames.map((name, i) => (
                  <li
                    key={i}
                    className="font-mono text-[11px] text-base-content/80"
                  >
                    {name}
                  </li>
                ))}
              </ul>
            ) : (
              <div className="text-base-content/60">
                {typedData.staleInputCount} input
                {typedData.staleInputCount === 1 ? "" : "s"} updated
              </div>
            )}
            <div className="text-base-content/60 mt-1">
              Recalibration recommended
            </div>
            <div className="absolute top-full left-1/2 -translate-x-1/2 w-0 h-0 border-l-[6px] border-r-[6px] border-t-[6px] border-l-transparent border-r-transparent border-t-base-100" />
          </div>
        </>
      )}
      <Handle
        type="target"
        position={Position.Top}
        className="!bg-secondary !w-2 !h-2"
      />
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-2 h-2 rounded-sm bg-secondary/60 flex-shrink-0" />
          <div
            className={`font-semibold truncate ${typedData.isTaskFlow ? "text-base" : "text-sm"}`}
          >
            {typedData.label}
          </div>
        </div>
        {typedData.isTaskFlow && typedData.qid && (
          <span className="badge badge-secondary badge-sm flex-shrink-0">
            {typedData.qid}
          </span>
        )}
      </div>
      {typedData.status && (
        <div className={`text-xs ${statusClass} mt-1 capitalize`}>
          {typedData.status}
        </div>
      )}
      {hasStaleInputs && (
        <div className="text-[10px] font-mono mt-1 rounded px-2 py-1 text-center bg-info/10 text-info">
          {typedData.staleInputCount} stale input
          {typedData.staleInputCount === 1 ? "" : "s"}
        </div>
      )}
      {typedData.taskId && !hasStaleInputs && (
        <div className="text-[10px] text-base-content/50 mt-1 truncate">
          Click to view details
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
  taskFlow: "#d946ef", // fuchsia-500 (task dependency)
  default: "#64748b", // slate-500
};

type ViewDetail = "full" | "taskFlow";

/**
 * Collapse entity nodes, keeping only activity nodes with direct
 * activity-to-activity edges inferred via shared entities.
 */
function collapseToTaskFlow(
  apiNodes: LineageNodeResponse[],
  apiEdges: LineageEdgeResponse[],
  directInputIds?: Set<string>,
): {
  nodes: LineageNodeResponse[];
  edges: LineageEdgeResponse[];
  staleInputsByActivity: Map<string, number>;
  staleInputNamesByActivity: Map<string, string[]>;
} {
  // Keep only activity nodes
  const activityNodes = apiNodes.filter((n) => n.node_type === "activity");

  // Index entity nodes by id for quick lookup
  const entityById = new Map(
    apiNodes.filter((n) => n.node_type === "entity").map((n) => [n.node_id, n]),
  );

  // Build maps: entity → generating activity, entity → consuming activities
  const entityToGenerator = new Map<string, string>();
  const entityToConsumers = new Map<string, string[]>();
  // activity → set of entity ids it used
  const activityUsedEntities = new Map<string, Set<string>>();

  for (const edge of apiEdges) {
    if (edge.relation_type === "wasGeneratedBy") {
      // source = entity, target = activity that generated it
      entityToGenerator.set(edge.source_id, edge.target_id);
    } else if (edge.relation_type === "used") {
      // source = activity, target = entity it consumed
      const consumers = entityToConsumers.get(edge.target_id) ?? [];
      consumers.push(edge.source_id);
      entityToConsumers.set(edge.target_id, consumers);
      // Track which entities each activity used
      const used = activityUsedEntities.get(edge.source_id) ?? new Set();
      used.add(edge.target_id);
      activityUsedEntities.set(edge.source_id, used);
    }
  }

  // Compute stale input counts and names per activity (only for direct inputs of origin)
  const staleInputsByActivity = new Map<string, number>();
  const staleInputNamesByActivity = new Map<string, string[]>();
  for (const [activityId, entityIds] of activityUsedEntities) {
    let staleCount = 0;
    const staleNames: string[] = [];
    for (const entityId of entityIds) {
      // Only count as stale if it's a direct input of the origin
      if (directInputIds && !directInputIds.has(entityId)) continue;
      const entity = entityById.get(entityId);
      if (entity?.latest_version != null && entity.entity?.version != null) {
        if (entity.latest_version > entity.entity.version) {
          staleCount++;
          const name = entity.entity?.parameter_name || entityId;
          const qid = entity.entity?.qid;
          staleNames.push(qid ? `${name}(${qid})` : name);
        }
      }
    }
    if (staleCount > 0) {
      staleInputsByActivity.set(activityId, staleCount);
      staleInputNamesByActivity.set(activityId, staleNames);
    }
  }

  // For each entity, create edges from the generator activity to each consumer activity
  const edgeSet = new Set<string>();
  const directEdges: LineageEdgeResponse[] = [];

  for (const [entityId, generatorId] of entityToGenerator) {
    const consumers = entityToConsumers.get(entityId) ?? [];
    for (const consumerId of consumers) {
      if (generatorId === consumerId) continue;
      const key = `${generatorId}->${consumerId}`;
      if (edgeSet.has(key)) continue;
      edgeSet.add(key);
      directEdges.push({
        source_id: consumerId,
        target_id: generatorId,
        relation_type: "taskFlow",
      });
    }
  }

  return {
    nodes: activityNodes,
    edges: directEdges,
    staleInputsByActivity,
    staleInputNamesByActivity,
  };
}

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
  opts?: {
    nodeWidth?: number;
    nodeHeight?: number;
    nodesep?: number;
    ranksep?: number;
    edgesep?: number;
    ranker?: string;
  },
): { nodes: Node[]; edges: Edge[] } {
  const nodeWidth = opts?.nodeWidth ?? 180;
  const nodeHeight = opts?.nodeHeight ?? 70;

  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));

  const isHorizontal = direction === "LR" || direction === "RL";
  dagreGraph.setGraph({
    rankdir: direction,
    nodesep: opts?.nodesep ?? 60,
    ranksep: opts?.ranksep ?? 80,
    edgesep: opts?.edgesep ?? 20,
    marginx: 40,
    marginy: 40,
    ...(opts?.ranker && { ranker: opts.ranker }),
  });

  // Add nodes to dagre
  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: nodeWidth, height: nodeHeight });
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
        x: dagreNode.x - nodeWidth / 2,
        y: dagreNode.y - nodeHeight / 2,
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
  isTaskFlow?: boolean,
  staleInputsByActivity?: Map<string, number>,
  directInputIds?: Set<string>,
  staleInputNamesByActivity?: Map<string, string[]>,
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
    let latestVersion: number | undefined;
    let hasNewerVersion: boolean | undefined;
    let nodeVersion: number | undefined;

    if (isEntity && node.entity) {
      label = node.entity.parameter_name || "?";
      value = formatValue(node.entity.value);
      unit = node.entity.unit;
      qid = node.entity.qid;
      nodeVersion = node.entity.version;
      // Only show staleness indicator for direct inputs of the origin
      const isDirectInput = !directInputIds || directInputIds.has(node.node_id);
      if (
        isDirectInput &&
        node.latest_version != null &&
        node.entity.version != null &&
        node.latest_version > node.entity.version
      ) {
        latestVersion = node.latest_version;
        hasNewerVersion = true;
      }
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

    // For activity nodes in task flow, propagate stale input info
    const staleInputCount =
      !isEntity && staleInputsByActivity
        ? (staleInputsByActivity.get(node.node_id) ?? 0)
        : 0;
    const staleInputNames =
      !isEntity && staleInputNamesByActivity
        ? (staleInputNamesByActivity.get(node.node_id) ?? [])
        : [];

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
        latestVersion,
        hasNewerVersion,
        nodeVersion,
        staleInputCount,
        staleInputNames,
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
      type: "default",
      style: {
        stroke: strokeColor,
        strokeWidth: isTaskFlow ? 2.5 : 1.5,
        opacity: isTaskFlow ? 1 : 0.7,
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: strokeColor,
        width: isTaskFlow ? 20 : 12,
        height: isTaskFlow ? 20 : 12,
      },
      animated: edge.relation_type === "wasDerivedFrom",
    };
  });

  // Apply dagre layout
  return getLayoutedElements(
    flowNodes,
    flowEdges,
    "TB",
    isTaskFlow
      ? {
          nodeWidth: 260,
          nodeHeight: 90,
          nodesep: 100,
          ranksep: 120,
          ranker: "tight-tree",
        }
      : {
          nodeWidth: 230,
          nodeHeight: 56,
          nodesep: 90,
          ranksep: 110,
          edgesep: 30,
          ranker: "network-simplex",
        },
  );
}

export function ProvenanceGraph({
  nodes: apiNodes,
  edges: apiEdges,
  originId,
}: ProvenanceGraphProps) {
  const [pinnedTask, setPinnedTask] = useState<{
    taskId: string;
    qid: string;
    taskName?: string;
    nodeId: string;
  } | null>(null);
  const [showDerivedEdges, setShowDerivedEdges] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [focusHops, setFocusHops] = useState(4);
  const [showAll, setShowAll] = useState(false);
  const [viewDetail, setViewDetail] = useState<ViewDetail>("full");

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

  // Compute direct input entity IDs for the origin parameter.
  // Only these entities should show staleness indicators.
  const directInputIds = useMemo(() => {
    if (!originId) return new Set<string>();
    // Find the activity that generated the origin entity
    const genEdge = constrainedApiEdges.find(
      (e) => e.relation_type === "wasGeneratedBy" && e.source_id === originId,
    );
    if (!genEdge) return new Set<string>();
    const generatingActivity = genEdge.target_id;
    // Find entities that the generating activity used
    const inputIds = new Set<string>();
    for (const e of constrainedApiEdges) {
      if (e.relation_type === "used" && e.source_id === generatingActivity) {
        inputIds.add(e.target_id);
      }
    }
    return inputIds;
  }, [originId, constrainedApiEdges]);

  // Apply Task Flow collapse when in taskFlow mode
  const {
    nodes: flowApiNodes,
    edges: flowApiEdges,
    staleInputsByActivity,
    staleInputNamesByActivity,
  } = useMemo(() => {
    if (viewDetail === "taskFlow") {
      return collapseToTaskFlow(
        constrainedApiNodes,
        constrainedApiEdges,
        directInputIds,
      );
    }
    return {
      nodes: constrainedApiNodes,
      edges: constrainedApiEdges,
      staleInputsByActivity: new Map<string, number>(),
      staleInputNamesByActivity: new Map<string, string[]>(),
    };
  }, [viewDetail, constrainedApiNodes, constrainedApiEdges, directInputIds]);

  const isTaskFlow = viewDetail === "taskFlow";

  const { nodes: baseNodes, edges: baseEdges } = useMemo(
    () =>
      convertToFlowElements(
        flowApiNodes,
        flowApiEdges,
        originId,
        isTaskFlow,
        staleInputsByActivity,
        directInputIds,
        staleInputNamesByActivity,
      ),
    [
      flowApiNodes,
      flowApiEdges,
      originId,
      isTaskFlow,
      staleInputsByActivity,
      directInputIds,
      staleInputNamesByActivity,
    ],
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
        !!pinnedTask?.nodeId &&
        node.id === pinnedTask.nodeId;
      return {
        ...node,
        data: {
          ...(node.data as Record<string, unknown>),
          isMatch,
          dimmed,
          isPinned,
          ...(node.type === "activity" && { isTaskFlow }),
        },
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
        style: {
          ...(edge.style as Record<string, unknown>),
          opacity: dimmed ? 0.15 : 1,
        },
      };
    });

    return { nodes: withDecorations, edges: withEdgeDimming };
  }, [
    baseNodes,
    baseEdges,
    matchingNodeIds,
    searchQuery,
    pinnedTask?.nodeId,
    isTaskFlow,
  ]);

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
      if (apiNode?.node_type === "activity") {
        const nodeData = node.data as Record<string, unknown>;
        const taskId = (nodeData?.taskId as string) || "";
        const qid = (nodeData.qid as string) || "0";
        const taskName =
          typeof nodeData.label === "string"
            ? (nodeData.label as string)
            : undefined;
        setPinnedTask((prev) => {
          if (prev?.nodeId === node.id) return null;
          return { taskId, qid, taskName, nodeId: node.id };
        });
      }
    },
    [apiNodes],
  );

  const visibleCounts = useMemo(() => {
    const entityCount = initialNodes.filter((n) => n.type === "entity").length;
    const taskCount = initialNodes.filter((n) => n.type === "activity").length;
    const failedTasks = initialNodes.filter(
      (n) =>
        n.type === "activity" &&
        (n.data as Record<string, unknown>)?.status === "failed",
    ).length;
    const lowConfidenceParams = initialNodes.filter(
      (n) =>
        n.type === "entity" &&
        (n.data as Record<string, unknown>)?.lowConfidence,
    ).length;
    const staleInputs = initialNodes.filter(
      (n) =>
        n.type === "entity" &&
        (n.data as Record<string, unknown>)?.hasNewerVersion,
    ).length;
    return {
      entityCount,
      taskCount,
      failedTasks,
      lowConfidenceParams,
      staleInputs,
    };
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

  return (
    <div className="h-[calc(100vh-16rem)] min-h-[500px] flex bg-base-200 rounded-lg border border-base-300 overflow-hidden">
      {/* Graph canvas */}
      <div className="flex-1 relative">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={handleNodeClick}
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
            <div className="join ml-2">
              <button
                className={`btn btn-xs join-item pointer-events-auto ${viewDetail === "full" ? "btn-active" : ""}`}
                onClick={() => setViewDetail("full")}
              >
                Detail
              </button>
              <button
                className={`btn btn-xs join-item pointer-events-auto ${viewDetail === "taskFlow" ? "btn-active" : ""}`}
                onClick={() => setViewDetail("taskFlow")}
              >
                Task Flow
              </button>
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
            {visibleCounts.staleInputs > 0 && (
              <span className="badge badge-info badge-sm">
                updated {visibleCounts.staleInputs}
              </span>
            )}
          </div>
        </div>

        {/* Legend */}
        <div className="absolute bottom-4 left-4 bg-base-100 p-3 rounded-lg shadow border border-base-300 text-xs">
          <div className="font-medium mb-2">Legend</div>
          <div className="flex gap-4">
            {viewDetail === "full" && (
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded bg-primary/20 border border-primary/50" />
                <span className="text-base-content/70">Parameter</span>
              </div>
            )}
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded bg-secondary/20 border border-secondary/50" />
              <span className="text-base-content/70">Task</span>
            </div>
          </div>
          {viewDetail === "full" ? (
            <>
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
              <div className="flex gap-4 mt-2 pt-2 border-t border-base-300">
                <div className="flex items-center gap-1.5">
                  <div className="w-4 h-0.5 bg-blue-500 rounded" />
                  <span className="text-base-content/60">derived</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <div className="px-1.5 py-0.5 rounded bg-info/10 text-info text-[9px] font-mono leading-none">
                    v1→v2
                  </div>
                  <span className="text-base-content/60">newer available</span>
                </div>
              </div>
            </>
          ) : (
            <div className="flex items-center gap-1.5 mt-2 pt-2 border-t border-base-300">
              <div className="w-4 h-0.5 bg-fuchsia-500 rounded" />
              <span className="text-base-content/60">task flow</span>
            </div>
          )}
        </div>
      </div>

      {/* Task Detail Panel */}
      {pinnedTask && (
        <TaskDetailPanel
          activityNodeId={pinnedTask.nodeId}
          nodes={apiNodes}
          edges={apiEdges}
          onClose={() => setPinnedTask(null)}
        />
      )}
    </div>
  );
}
