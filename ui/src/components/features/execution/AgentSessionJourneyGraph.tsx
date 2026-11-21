"use client";

import { useMemo } from "react";

import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Panel,
  Position,
  ReactFlow,
  ReactFlowProvider,
} from "@xyflow/react";

import type { Edge, Node, NodeProps, NodeTypes } from "@xyflow/react";

import type { AgentJourneyEdge, AgentJourneyEdgeKind, AgentJourneyNode } from "@/schemas";

import "@xyflow/react/dist/style.css";

import { EDGE_COLOR, getStatusClasses } from "./ExecutionDAG";

const FIT_VIEW_OPTIONS = { padding: 0.1, minZoom: 0.1, maxZoom: 1.5 };
const COLUMN_WIDTH = 230;
const NODE_WIDTH = 190;
const NODE_HEIGHT = 64;
/** One lane per kind of step, so measurements, judgments, and people never overlap. */
const LANE_Y: Record<string, number> = {
  measurement: 0,
  proposal: 0,
  session_action: 0,
  decision: 130,
  intervention: 260,
};

export const KIND_LABELS: Record<string, string> = {
  measurement: "Measurement",
  proposal: "Rejected proposal",
  session_action: "Session action",
  decision: "Agent decision",
  intervention: "Expert",
};

/** How each edge kind reads; `sequence` is temporal only, every other kind is a recorded link. */
export const EDGE_KIND_LABELS: Record<AgentJourneyEdgeKind, string> = {
  sequence: "Dispatched next",
  evidence: "Evidence for",
  next_action: "Chose next",
  retry_of: "Repeated as",
  escalation: "Asked an expert",
  follow_up: "Follow-up",
};

const CAUSAL_COLOR = "color-mix(in oklch, var(--color-base-content) 75%, transparent)";
const SEQUENCE_COLOR = "color-mix(in oklch, var(--color-base-content) 30%, transparent)";

function nodeClasses(node: AgentJourneyNode): string {
  switch (node.kind) {
    case "measurement":
      return getStatusClasses(node.status);
    case "proposal":
      return "border-dashed border-base-content/40 bg-base-100 text-base-content/60";
    case "decision":
      return node.status === "superseded"
        ? "border-dashed border-base-content/30 bg-base-100 text-base-content/60"
        : "border-base-content/40 bg-base-100 text-base-content";
    case "intervention":
      return node.status === "open" || node.status === "responding"
        ? "border-warning bg-warning/10 text-warning"
        : "border-base-content/40 bg-base-100 text-base-content";
    default:
      return "border-base-300 bg-base-200 text-base-content/60";
  }
}

interface JourneyNodeData extends Record<string, unknown> {
  node: AgentJourneyNode;
  isSelected: boolean;
}

function JourneyNodeView({ data }: NodeProps) {
  const { node, isSelected } = data as JourneyNodeData;
  return (
    <div
      className={`flex h-[64px] w-[190px] cursor-pointer flex-col justify-center rounded-[var(--radius-field)] border-2 px-3 shadow-xs ${nodeClasses(node)} ${isSelected ? "ring-2 ring-primary ring-offset-2 ring-offset-base-200" : ""}`}
      aria-current={isSelected ? "true" : undefined}
    >
      <Handle type="target" position={Position.Left} />
      <div className="truncate text-xs text-base-content/60">
        {node.order + 1}. {KIND_LABELS[node.kind] ?? node.kind}
      </div>
      <div className="truncate text-sm font-medium">{node.label}</div>
      <div className="truncate text-xs">{node.status.replace(/_/g, " ")}</div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

const nodeTypes: NodeTypes = { journey: JourneyNodeView };

function edgeStyle(kind: AgentJourneyEdgeKind) {
  if (kind === "sequence") {
    return { stroke: SEQUENCE_COLOR, strokeWidth: 1.5, strokeDasharray: "6 4" };
  }
  if (kind === "retry_of") {
    return { stroke: CAUSAL_COLOR, strokeWidth: 2, strokeDasharray: "2 3" };
  }
  return { stroke: CAUSAL_COLOR, strokeWidth: 2 };
}

interface AgentSessionJourneyGraphProps {
  nodes: AgentJourneyNode[];
  edges: AgentJourneyEdge[];
  selectedNodeId: string | null;
  onSelect: (nodeId: string) => void;
}

/**
 * The journey as a graph: time runs left to right, one lane per kind of step. Dashed edges are
 * only the dispatch order; solid edges are links the records name (evidence, next action,
 * escalation, follow-up), and dotted edges a declared repeat. No edge is inferred from time.
 */
export function AgentSessionJourneyGraph({
  nodes,
  edges,
  selectedNodeId,
  onSelect,
}: AgentSessionJourneyGraphProps) {
  const firstOrder = nodes[0]?.order ?? 0;
  const flowNodes = useMemo<Node[]>(
    () =>
      nodes.map((node) => ({
        id: node.node_id,
        type: "journey",
        position: { x: (node.order - firstOrder) * COLUMN_WIDTH, y: LANE_Y[node.kind] ?? 0 },
        data: { node, isSelected: node.node_id === selectedNodeId } satisfies JourneyNodeData,
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
      })),
    [firstOrder, nodes, selectedNodeId],
  );
  const flowEdges = useMemo<Edge[]>(
    () =>
      edges.map((edge) => ({
        id: edge.edge_id,
        source: edge.source,
        target: edge.target,
        type: "smoothstep",
        label: edge.kind === "sequence" ? undefined : EDGE_KIND_LABELS[edge.kind],
        labelStyle: { fontSize: 12 },
        style: edgeStyle(edge.kind),
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: edge.kind === "sequence" ? SEQUENCE_COLOR : EDGE_COLOR,
        },
        data: { kind: edge.kind },
      })),
    [edges],
  );

  return (
    <div className="h-[480px]" data-testid="agent-journey-canvas">
      <ReactFlowProvider>
        <ReactFlow
          nodes={flowNodes}
          edges={flowEdges}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={FIT_VIEW_OPTIONS}
          minZoom={0.1}
          maxZoom={1.5}
          className="bg-base-200"
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          onNodeClick={(_, node) => onSelect(node.id)}
        >
          <Background />
          <Controls showInteractive={false} fitViewOptions={FIT_VIEW_OPTIONS} />
          <Panel position="top-left" className="rounded bg-base-100 p-2 text-xs">
            <div className="flex flex-col gap-1">
              <span className="flex items-center gap-2">
                <svg width="28" height="6" aria-hidden="true">
                  <line x1="0" y1="3" x2="28" y2="3" style={edgeStyle("sequence")} />
                </svg>
                Dispatch order, time only
              </span>
              <span className="flex items-center gap-2">
                <svg width="28" height="6" aria-hidden="true">
                  <line x1="0" y1="3" x2="28" y2="3" style={edgeStyle("evidence")} />
                </svg>
                Recorded link: evidence, next step, expert
              </span>
              <span className="flex items-center gap-2">
                <svg width="28" height="6" aria-hidden="true">
                  <line x1="0" y1="3" x2="28" y2="3" style={edgeStyle("retry_of")} />
                </svg>
                Declared repeat
              </span>
            </div>
          </Panel>
        </ReactFlow>
      </ReactFlowProvider>
    </div>
  );
}
