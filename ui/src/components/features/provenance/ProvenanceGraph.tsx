"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
} from "@xyflow/react";
import dagre from "dagre";

import type { Edge, Node, NodeProps, NodeTypes } from "@xyflow/react";

import { QubitTile } from "@/components/ui/QubitTile";
import { formatParameterValue } from "@/lib/formatParameterValue";
import type { LineageEdgeResponse, LineageNodeResponse } from "@/schemas";

import { TaskDetailPanel } from "./TaskDetailPanel";
import "@xyflow/react/dist/style.css";

interface ProvenanceGraphProps {
  nodes: LineageNodeResponse[];
  edges: LineageEdgeResponse[];
  /** Entity the graph was opened on; it is marked and the depth is measured from it. */
  originId?: string;
}

type View = "values" | "tasks";

/** Hops shown by default: the origin, its task, that task's inputs and the tasks that wrote them. */
const DEFAULT_DEPTH = 3;
const DEPTH_CHOICES = [1, 2, 3, 4, 6, 8];
/** Relative error at or above which a value is marked as uncertain. */
const UNCERTAIN_RATIO = 0.05;

const EDGE_COLOR = "color-mix(in oklch, var(--color-base-content) 35%, transparent)";
const DIM_OPACITY = 0.2;

interface ValueNodeData extends Record<string, unknown> {
  label: string;
  qid?: string;
  valueText: string;
  isOrigin: boolean;
  uncertain: boolean;
  /** Set when a newer version of a direct input exists; the origin was computed from a stale one. */
  newerVersion?: { from: number; to: number };
  isMatch: boolean;
  dimmed: boolean;
}

interface TaskNodeData extends Record<string, unknown> {
  label: string;
  qid?: string;
  status?: string;
  taskId?: string;
  staleInputs: string[];
  isMatch: boolean;
  dimmed: boolean;
  isSelected: boolean;
}

function nodeFrame(isMatch: boolean, dimmed: boolean, extra = "") {
  return `rounded-lg border bg-base-100 px-3 py-2 text-xs transition-opacity ${
    isMatch ? "outline outline-2 outline-primary outline-offset-2" : ""
  } ${dimmed ? "opacity-20" : ""} ${extra}`;
}

function ValueNode({ data }: NodeProps) {
  const node = data as ValueNodeData;
  return (
    <div
      className={nodeFrame(
        node.isMatch,
        node.dimmed,
        node.isOrigin ? "border-2 border-primary" : "border-base-300",
      )}
      style={{ width: 220 }}
      title={node.newerVersion ? "A newer version of this input exists" : undefined}
    >
      <Handle type="target" position={Position.Top} className="!h-1.5 !w-1.5 !bg-base-content/40" />
      <div className="flex items-center gap-2">
        <span className="min-w-0 flex-1 truncate font-medium">{node.label}</span>
        {node.qid && <QubitTile qid={node.qid} />}
      </div>
      <div className="mt-0.5 flex items-center justify-between gap-2 font-mono">
        <span className={`truncate ${node.uncertain ? "text-warning" : "text-base-content/70"}`}>
          {node.valueText}
        </span>
        {node.newerVersion && (
          <span className="shrink-0 text-warning">
            v{node.newerVersion.from} → v{node.newerVersion.to}
          </span>
        )}
      </div>
      <Handle
        type="source"
        position={Position.Bottom}
        className="!h-1.5 !w-1.5 !bg-base-content/40"
      />
    </div>
  );
}

function TaskNode({ data }: NodeProps) {
  const node = data as TaskNodeData;
  const statusClass = node.status === "failed" ? "text-error" : "text-base-content/50";
  return (
    <div
      className={nodeFrame(
        node.isMatch,
        node.dimmed,
        `cursor-pointer !bg-base-200 ${node.isSelected ? "border-base-content/60" : "border-base-300"}`,
      )}
      style={{ width: 200 }}
      title={
        node.staleInputs.length > 0
          ? `Newer versions exist for: ${node.staleInputs.join(", ")}`
          : "Select to see what this task read and wrote"
      }
    >
      <Handle type="target" position={Position.Top} className="!h-1.5 !w-1.5 !bg-base-content/40" />
      <div className="flex items-center gap-2">
        <span className="min-w-0 flex-1 truncate font-medium">{node.label}</span>
        {node.qid && <QubitTile qid={node.qid} />}
      </div>
      <div className="mt-0.5 flex items-center justify-between gap-2">
        <span className={statusClass}>{node.status ?? "task"}</span>
        {node.staleInputs.length > 0 && (
          <span className="text-warning">
            {node.staleInputs.length} input{node.staleInputs.length === 1 ? "" : "s"} updated
          </span>
        )}
      </div>
      <Handle
        type="source"
        position={Position.Bottom}
        className="!h-1.5 !w-1.5 !bg-base-content/40"
      />
    </div>
  );
}

const nodeTypes: NodeTypes = { value: ValueNode, task: TaskNode };

const FIT_PADDING = 0.08;
const FIT_DURATION_MS = 300;

/**
 * Glides the viewport to the graph whenever its shape changes: a new depth or view re-fits the
 * whole graph, a search fits the matches, and opening the side panel re-fits the narrower canvas.
 * Selecting a node is deliberately not a trigger, so the view stays put under the pointer.
 */
function ViewportFitter({
  layoutKey,
  focusIds,
  panelOpen,
}: {
  layoutKey: string;
  focusIds: string[];
  panelOpen: boolean;
}) {
  const { fitView } = useReactFlow();
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      void fitView(
        focusIds.length > 0
          ? {
              nodes: focusIds.map((id) => ({ id })),
              padding: 0.5,
              maxZoom: 1,
              duration: FIT_DURATION_MS,
            }
          : { padding: FIT_PADDING, duration: FIT_DURATION_MS },
      );
    });
    return () => cancelAnimationFrame(frame);
  }, [layoutKey, focusIds, panelOpen, fitView]);
  return null;
}

function nodeMatches(node: LineageNodeResponse, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) return false;
  const parts = [node.node_id];
  if (node.entity) {
    parts.push(
      node.entity.parameter_name,
      node.entity.qid ?? "",
      node.entity.unit ?? "",
      String(node.entity.value ?? ""),
    );
  }
  if (node.activity) {
    parts.push(node.activity.task_name, node.activity.status ?? "", node.activity.qid ?? "");
  }
  return parts.join(" ").toLowerCase().includes(needle);
}

/** Undirected hop distance from the origin, so depth is the same whichever way an edge points. */
function hopDistances(originId: string, edges: LineageEdgeResponse[]): Map<string, number> {
  const adjacency = new Map<string, Set<string>>();
  const link = (from: string, to: string) => {
    if (!adjacency.has(from)) adjacency.set(from, new Set());
    adjacency.get(from)!.add(to);
  };
  for (const edge of edges) {
    link(edge.source_id, edge.target_id);
    link(edge.target_id, edge.source_id);
  }
  const distance = new Map<string, number>([[originId, 0]]);
  const queue = [originId];
  while (queue.length > 0) {
    const current = queue.shift()!;
    for (const next of adjacency.get(current) ?? []) {
      if (!distance.has(next)) {
        distance.set(next, distance.get(current)! + 1);
        queue.push(next);
      }
    }
  }
  return distance;
}

/** Inputs of the task that produced the origin: the only values whose staleness matters here. */
function directInputsOf(originId: string, edges: LineageEdgeResponse[]): Set<string> {
  const generated = edges.find(
    (edge) => edge.relation_type === "wasGeneratedBy" && edge.source_id === originId,
  );
  if (!generated) return new Set();
  return new Set(
    edges
      .filter((edge) => edge.relation_type === "used" && edge.source_id === generated.target_id)
      .map((edge) => edge.target_id),
  );
}

/** Collapse values away, leaving tasks joined wherever one task wrote what another read. */
function tasksOnly(
  nodes: LineageNodeResponse[],
  edges: LineageEdgeResponse[],
): { nodes: LineageNodeResponse[]; edges: LineageEdgeResponse[] } {
  const generator = new Map<string, string>();
  const consumers = new Map<string, string[]>();
  for (const edge of edges) {
    if (edge.relation_type === "wasGeneratedBy") generator.set(edge.source_id, edge.target_id);
    if (edge.relation_type === "used") {
      consumers.set(edge.target_id, [...(consumers.get(edge.target_id) ?? []), edge.source_id]);
    }
  }
  const seen = new Set<string>();
  const flow: LineageEdgeResponse[] = [];
  for (const [entityId, producer] of generator) {
    for (const consumer of consumers.get(entityId) ?? []) {
      const key = `${consumer}>${producer}`;
      if (consumer === producer || seen.has(key)) continue;
      seen.add(key);
      flow.push({ source_id: consumer, target_id: producer, relation_type: "taskFlow" });
    }
  }
  return { nodes: nodes.filter((node) => node.node_type === "activity"), edges: flow };
}

function layout(nodes: Node[], edges: Edge[]): Node[] {
  const graph = new dagre.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({ rankdir: "TB", nodesep: 28, ranksep: 56, marginx: 16, marginy: 16 });
  for (const node of nodes) {
    graph.setNode(node.id, { width: node.type === "value" ? 220 : 200, height: 52 });
  }
  for (const edge of edges) graph.setEdge(edge.source, edge.target);
  dagre.layout(graph);
  return nodes.map((node) => {
    const placed = graph.node(node.id);
    const width = node.type === "value" ? 220 : 200;
    return { ...node, position: { x: placed.x - width / 2, y: placed.y - 26 } };
  });
}

/**
 * Every value the origin derives from, drawn as a graph: values (rounded cards) alternate with the
 * tasks (grey cards) that read and wrote them. Depth, search and a tasks-only view keep a long
 * calibration chain readable; selecting a task opens what it read and wrote.
 */
export function ProvenanceGraph({
  nodes: apiNodes,
  edges: apiEdges,
  originId,
}: ProvenanceGraphProps) {
  const [query, setQuery] = useState("");
  const [depth, setDepth] = useState<number | "all">(DEFAULT_DEPTH);
  const [view, setView] = useState<View>("values");
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);

  // Derivation edges duplicate what the task edges already say; the graph draws tasks only.
  const structuralEdges = useMemo(
    () => apiEdges.filter((edge) => edge.relation_type !== "wasDerivedFrom"),
    [apiEdges],
  );
  const distances = useMemo(
    () => (originId ? hopDistances(originId, structuralEdges) : new Map<string, number>()),
    [originId, structuralEdges],
  );
  const maxDepth = useMemo(() => Math.max(0, ...distances.values()), [distances]);
  const directInputs = useMemo(
    () => (originId ? directInputsOf(originId, structuralEdges) : new Set<string>()),
    [originId, structuralEdges],
  );
  const matches = useMemo(
    () => new Set(apiNodes.filter((node) => nodeMatches(node, query)).map((node) => node.node_id)),
    [apiNodes, query],
  );

  // A search shows the whole graph so a match outside the current depth is not hidden.
  const limit = matches.size > 0 || depth === "all" ? Number.POSITIVE_INFINITY : depth;
  const shown = useMemo(() => {
    const nodes = originId
      ? apiNodes.filter((node) => (distances.get(node.node_id) ?? Infinity) <= limit)
      : apiNodes;
    const ids = new Set(nodes.map((node) => node.node_id));
    const edges = structuralEdges.filter(
      (edge) => ids.has(edge.source_id) && ids.has(edge.target_id),
    );
    return view === "tasks" ? tasksOnly(nodes, edges) : { nodes, edges };
  }, [apiNodes, structuralEdges, distances, limit, originId, view]);

  const staleInputsByTask = useMemo(() => {
    const byId = new Map(apiNodes.map((node) => [node.node_id, node]));
    const result = new Map<string, string[]>();
    for (const edge of structuralEdges) {
      if (edge.relation_type !== "used" || !directInputs.has(edge.target_id)) continue;
      const input = byId.get(edge.target_id);
      if (!input?.entity || input.latest_version == null) continue;
      if (input.latest_version > input.entity.version) {
        const name = `${input.entity.parameter_name} ${input.entity.qid ?? ""}`.trim();
        result.set(edge.source_id, [...(result.get(edge.source_id) ?? []), name]);
      }
    }
    return result;
  }, [apiNodes, structuralEdges, directInputs]);

  const { nodes: initialNodes, edges: initialEdges } = useMemo(() => {
    const neighbourhood = new Set(matches);
    for (const edge of shown.edges) {
      if (matches.has(edge.source_id) || matches.has(edge.target_id)) {
        neighbourhood.add(edge.source_id);
        neighbourhood.add(edge.target_id);
      }
    }
    const dim = (id: string) => matches.size > 0 && !neighbourhood.has(id);

    const flowNodes: Node[] = shown.nodes.map((node) => {
      if (node.entity) {
        const entity = node.entity;
        const error = typeof entity.error === "number" ? entity.error : 0;
        const value = typeof entity.value === "number" ? entity.value : null;
        const uncertain =
          error !== 0 &&
          value !== null &&
          (value === 0 || Math.abs(error / value) >= UNCERTAIN_RATIO);
        const stale =
          directInputs.has(node.node_id) &&
          node.latest_version != null &&
          node.latest_version > entity.version;
        const data: ValueNodeData = {
          label: entity.parameter_name,
          qid: entity.qid,
          valueText: formatParameterValue(entity.value, entity.unit),
          isOrigin: node.node_id === originId,
          uncertain,
          newerVersion: stale ? { from: entity.version, to: node.latest_version! } : undefined,
          isMatch: matches.has(node.node_id),
          dimmed: dim(node.node_id),
        };
        return { id: node.node_id, type: "value", position: { x: 0, y: 0 }, data };
      }
      const data: TaskNodeData = {
        label: node.activity?.task_name ?? node.node_id,
        qid: node.activity?.qid || undefined,
        status: node.activity?.status || undefined,
        taskId: node.activity?.task_id,
        staleInputs: staleInputsByTask.get(node.node_id) ?? [],
        isMatch: matches.has(node.node_id),
        dimmed: dim(node.node_id),
        isSelected: node.node_id === selectedTaskId,
      };
      return { id: node.node_id, type: "task", position: { x: 0, y: 0 }, data };
    });

    const flowEdges: Edge[] = shown.edges.map((edge, index) => ({
      id: `edge-${index}`,
      source: edge.source_id,
      target: edge.target_id,
      type: "smoothstep",
      style: {
        stroke: EDGE_COLOR,
        strokeWidth: 1.25,
        opacity: dim(edge.source_id) || dim(edge.target_id) ? DIM_OPACITY : 1,
      },
      markerEnd: { type: MarkerType.ArrowClosed, color: EDGE_COLOR, width: 14, height: 14 },
    }));

    return { nodes: layout(flowNodes, flowEdges), edges: flowEdges };
  }, [shown, matches, directInputs, originId, staleInputsByTask, selectedTaskId]);

  const matchIds = useMemo(() => [...matches].sort(), [matches]);
  const layoutKey = `${view}:${limit}:${shown.nodes.length}`;

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  useEffect(() => {
    setNodes(initialNodes);
    setEdges(initialEdges);
  }, [initialNodes, initialEdges, setNodes, setEdges]);

  const handleNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    if (node.type !== "task") return;
    setSelectedTaskId((current) => (current === node.id ? null : node.id));
  }, []);

  const counts = useMemo(() => {
    const values = shown.nodes.filter((node) => node.node_type === "entity").length;
    const tasks = shown.nodes.length - values;
    const failed = shown.nodes.filter((node) => node.activity?.status === "failed").length;
    const stale = [...directInputs].filter((id) => {
      const node = apiNodes.find((candidate) => candidate.node_id === id);
      return (
        node?.entity && node.latest_version != null && node.latest_version > node.entity.version
      );
    }).length;
    return { values, tasks, failed, stale };
  }, [shown.nodes, directInputs, apiNodes]);

  if (apiNodes.length === 0) {
    return (
      <p className="flex h-full min-h-[320px] items-center justify-center text-sm text-base-content/60">
        No lineage is recorded for this value.
      </p>
    );
  }

  const depthChoices = DEPTH_CHOICES.filter((choice) => choice < maxDepth);

  return (
    <div className="flex h-full min-h-[480px] flex-col overflow-hidden rounded-lg border border-base-300">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-base-300 bg-base-100 px-3 py-2 text-xs">
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Find a value or task"
          aria-label="Find a value or task"
          className="input input-bordered input-xs w-48"
        />
        {originId && maxDepth > 1 && (
          <label className="flex items-center gap-1.5">
            <span className="text-base-content/60">Depth</span>
            <select
              aria-label="Depth"
              className="select select-bordered select-xs"
              value={depth === "all" || depth >= maxDepth ? "all" : depth}
              onChange={(event) =>
                setDepth(event.target.value === "all" ? "all" : Number(event.target.value))
              }
              disabled={matches.size > 0}
            >
              {depthChoices.map((choice) => (
                <option key={choice} value={choice}>
                  {choice} hop{choice === 1 ? "" : "s"}
                </option>
              ))}
              <option value="all">All ({maxDepth} hops)</option>
            </select>
          </label>
        )}
        <div className="tabs tabs-boxed bg-base-200" role="tablist" aria-label="Graph view">
          {(["values", "tasks"] as const).map((choice) => (
            <button
              key={choice}
              type="button"
              role="tab"
              aria-selected={view === choice}
              className={`tab tab-xs ${view === choice ? "tab-active" : ""}`}
              onClick={() => setView(choice)}
            >
              {choice === "values" ? "Values and tasks" : "Tasks only"}
            </button>
          ))}
        </div>
        <p className="ml-auto text-base-content/60">
          {shown.nodes.length} of {apiNodes.length} nodes
          {view === "values" ? `, ${counts.values} values and ${counts.tasks} tasks` : ""}
          {counts.failed > 0 && <span className="text-error">, {counts.failed} failed</span>}
          {counts.stale > 0 && (
            <span className="text-warning">
              , {counts.stale} input{counts.stale === 1 ? "" : "s"} updated since
            </span>
          )}
          . Arrows point from a result to what it came from.
        </p>
      </div>

      <div className="flex min-h-0 flex-1">
        <div className="relative min-w-0 flex-1 bg-base-200/60">
          <ReactFlowProvider>
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onNodeClick={handleNodeClick}
              nodeTypes={nodeTypes}
              fitView
              fitViewOptions={{ padding: FIT_PADDING }}
              minZoom={0.1}
              maxZoom={2}
              proOptions={{ hideAttribution: true }}
            >
              <Background color="currentColor" className="text-base-content/10" gap={20} size={1} />
              <Controls
                className="!rounded-lg !border-base-300 !bg-base-100 !shadow-none"
                showInteractive={false}
              />
              <ViewportFitter
                layoutKey={layoutKey}
                focusIds={matchIds}
                panelOpen={selectedTaskId !== null}
              />
            </ReactFlow>
          </ReactFlowProvider>
        </div>
        {selectedTaskId && (
          <TaskDetailPanel
            activityNodeId={selectedTaskId}
            nodes={apiNodes}
            edges={apiEdges}
            onClose={() => setSelectedTaskId(null)}
          />
        )}
      </div>
    </div>
  );
}
