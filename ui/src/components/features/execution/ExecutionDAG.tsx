"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import {
  ReactFlow,
  Background,
  Controls,
  Handle,
  Position,
  ReactFlowProvider,
  Panel,
  MarkerType,
  useReactFlow,
} from "@xyflow/react";
import dagre from "dagre";

import type { Node, Edge, NodeProps, NodeTypes } from "@xyflow/react";

import { TaskResultPreviewSidebar } from "@/components/features/task-results/TaskResultPreviewSidebar";
import {
  GridFullscreenButton,
  gridFullscreenPanelClass,
} from "@/components/ui/GridFullscreenButton";
import { useFullscreenPanel } from "@/hooks/useFullscreenPanel";
import { formatDateTime } from "@/lib/utils/datetime";
import "@xyflow/react/dist/style.css";

const FIT_VIEW_OPTIONS = { padding: 0.05, minZoom: 0.1, maxZoom: 1.5 };
/** Matches the sidebar's slide and the canvas margin transition (Tailwind `duration-300`). */
const PREVIEW_TRANSITION_MS = 300;

interface TaskNode {
  task_id: string;
  name: string;
  status: string;
  upstream_id?: string;
  start_at?: string;
  elapsed_time?: string;
  figure_path?: string[];
  input_parameters?: Record<string, unknown>;
  output_parameters?: Record<string, unknown>;
}

const getStatusStyles = (status: string) => {
  switch (status) {
    case "running":
      return {
        background: "hsl(198 93% 60% / 0.1)",
        borderColor: "hsl(198 93% 60%)",
        color: "hsl(198 93% 60%)",
      };
    case "completed":
      return {
        background: "hsl(142 71% 45% / 0.1)",
        borderColor: "hsl(142 71% 45%)",
        color: "hsl(142 71% 45%)",
      };
    case "scheduled":
      return {
        background: "hsl(48 96% 53% / 0.1)",
        borderColor: "hsl(48 96% 53%)",
        color: "hsl(48 96% 53%)",
      };
    case "failed":
      return {
        background: "hsl(0 91% 71% / 0.1)",
        borderColor: "hsl(0 91% 71%)",
        color: "hsl(0 91% 71%)",
      };
    case "cancelled":
      return {
        background: "hsl(220 9% 46% / 0.1)",
        borderColor: "hsl(220 9% 46%)",
        color: "hsl(220 9% 46%)",
      };
    default:
      return {
        background: "hsl(220 13% 91%)",
        borderColor: "hsl(220 13% 91%)",
        color: "hsl(220 9% 46%)",
      };
  }
};

interface NodeData extends Record<string, unknown> {
  name: string;
  status: string;
  startAt?: string;
  elapsedTime?: string;
  /** True while this node's result is open in the preview sidebar. */
  isSelected: boolean;
}

const CustomNode = ({ data }: NodeProps) => {
  const nodeData = data as NodeData;
  return (
    <div
      className={`group relative cursor-pointer rounded-lg border px-4 shadow-lg transition-shadow ${
        nodeData.isSelected ? "ring-2 ring-primary ring-offset-2 ring-offset-base-200" : ""
      }`}
      aria-current={nodeData.isSelected ? "true" : undefined}
      style={{
        ...getStatusStyles(nodeData.status),
        borderWidth: "2px",
        minWidth: "150px",
        maxWidth: "300px",
        height: "60px", // Fixed height
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
      }}
    >
      <Handle type="target" position={Position.Left} />
      <div className="font-medium truncate">{nodeData.name}</div>
      <div className="text-sm font-medium truncate">{nodeData.status}</div>
      {nodeData.startAt && (
        <div className="tooltip tooltip-bottom absolute -bottom-12 opacity-0 group-hover:opacity-100 transition-opacity bg-base-300 p-2 rounded text-xs whitespace-nowrap z-10">
          <div>Start: {formatDateTime(nodeData.startAt)}</div>
          {nodeData.elapsedTime && <div>Duration: {nodeData.elapsedTime}</div>}
        </div>
      )}
      <Handle type="source" position={Position.Right} />
    </div>
  );
};

const nodeTypes: NodeTypes = {
  custom: CustomNode,
};

interface ExecutionDAGProps {
  tasks: TaskNode[];
}

/**
 * React Flow canvas for the execution graph. Starts locked so the page scrolls normally;
 * the Controls lock button toggles pan, zoom and node dragging.
 */
function FlowContent({
  nodes,
  edges,
  onSelectTask,
  isFullscreen,
  isPreviewOpen,
}: {
  nodes: Node[];
  edges: Edge[];
  onSelectTask: (taskId: string) => void;
  isFullscreen: boolean;
  isPreviewOpen: boolean;
}) {
  const { fitView } = useReactFlow();
  const [isLocked, setIsLocked] = useState(true);

  // Re-fit whenever the container size (fullscreen toggle) changes.
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      fitView({ ...FIT_VIEW_OPTIONS, duration: 0 });
    });
    return () => cancelAnimationFrame(frame);
  }, [isFullscreen, fitView]);

  // The canvas gives up width to the preview sidebar with a CSS transition; once that has
  // finished, glide the graph into the space that is left. The initial fit is handled above.
  const previousPreviewOpen = useRef(isPreviewOpen);
  useEffect(() => {
    if (previousPreviewOpen.current === isPreviewOpen) return;
    previousPreviewOpen.current = isPreviewOpen;
    const timer = setTimeout(() => {
      fitView({ ...FIT_VIEW_OPTIONS, duration: PREVIEW_TRANSITION_MS });
    }, PREVIEW_TRANSITION_MS + 50);
    return () => clearTimeout(timer);
  }, [isPreviewOpen, fitView]);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      fitView
      className="bg-base-200"
      minZoom={0.1}
      maxZoom={1.5}
      zoomOnScroll={!isLocked}
      panOnScroll={false}
      panOnDrag={!isLocked}
      zoomOnPinch={!isLocked}
      zoomOnDoubleClick={!isLocked}
      preventScrolling={!isLocked}
      nodesDraggable={!isLocked}
      nodesConnectable={false}
      elementsSelectable={!isLocked}
      defaultEdgeOptions={{
        type: "smoothstep",
        animated: true,
        style: { strokeWidth: 2 },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: "#64748b",
        },
      }}
      fitViewOptions={FIT_VIEW_OPTIONS}
      onNodeClick={(_, node) => onSelectTask(node.id)}
    >
      <Background />
      <Controls showInteractive onInteractiveChange={(interactive) => setIsLocked(!interactive)} />
      <Panel position="top-left" className="bg-base-100 p-2 rounded flex items-center gap-2">
        <div className="text-sm">Select a node to preview its result</div>
        <button
          type="button"
          onClick={() => fitView({ ...FIT_VIEW_OPTIONS, duration: 300 })}
          className="btn btn-sm btn-ghost"
          title="Fit to view"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-4 w-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 8V4m0 0h4M4 4l5 5m11-1V4m-4 0h4m0 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"
            />
          </svg>
        </button>
      </Panel>
    </ReactFlow>
  );
}

/**
 * Execution task graph with fullscreen support. Selecting a node opens the selected task's result
 * in the same preview sidebar the Task Results page uses.
 */
export function ExecutionDAG({ tasks }: ExecutionDAGProps) {
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const { isFullscreen, toggleFullscreen } = useFullscreenPanel();

  const layout = useMemo(() => {
    const dagreGraph = new dagre.graphlib.Graph();
    dagreGraph.setDefaultEdgeLabel(() => ({}));
    dagreGraph.setGraph({
      rankdir: "LR",
      nodesep: 80,
      ranksep: 200,
      ranker: "network-simplex",
    });

    // Create initial nodes and edges
    const initialNodes: Node[] = tasks.map((task) => ({
      id: task.task_id,
      type: "custom",
      position: { x: 0, y: 0 },
      data: {
        name: task.name,
        status: task.status,
        startAt: task.start_at,
        elapsedTime: task.elapsed_time,
        isSelected: false,
      } satisfies NodeData,
      width: 180,
      height: 60,
    }));

    const initialEdges: Edge[] = tasks
      .filter(
        (task): task is TaskNode & { upstream_id: string } =>
          typeof task.upstream_id === "string" && task.upstream_id !== "",
      )
      .map((task) => ({
        id: `${task.upstream_id}-${task.task_id}`,
        source: task.upstream_id,
        target: task.task_id,
        type: "smoothstep",
        animated: true,
        style: { stroke: "#64748b", strokeWidth: 2 },
      }));

    // Add nodes and edges to dagre graph
    initialNodes.forEach((node) => {
      dagreGraph.setNode(node.id, { width: node.width, height: node.height });
    });

    initialEdges.forEach((edge) => {
      dagreGraph.setEdge(edge.source, edge.target);
    });

    // Calculate layout
    dagre.layout(dagreGraph);

    // Apply layout to nodes
    const nodes = initialNodes.map((node) => {
      const nodeWithPosition = dagreGraph.node(node.id);
      return {
        ...node,
        position: {
          x: nodeWithPosition.x - node.width! / 2,
          y: nodeWithPosition.y - node.height! / 2,
        },
      };
    });

    return { nodes, edges: initialEdges };
  }, [tasks]);

  const nodes = useMemo(
    () =>
      layout.nodes.map((node) => ({
        ...node,
        data: { ...node.data, isSelected: node.id === selectedTaskId },
      })),
    [layout.nodes, selectedTaskId],
  );
  const { edges } = layout;

  return (
    <div className={isFullscreen ? gridFullscreenPanelClass : ""}>
      {isFullscreen && (
        <div className="flex flex-wrap items-center justify-between gap-2 shrink-0">
          <h2 className="text-sm font-medium">Execution Flow</h2>
        </div>
      )}

      <div className={isFullscreen ? "flex-1 min-h-0" : "h-[600px]"}>
        <ReactFlowProvider>
          <div
            data-testid="execution-flow-canvas"
            className={`relative h-full transition-[margin] duration-300 ${
              // The sidebar is 40vw wide; subtract what already separates the canvas from the
              // viewport edge (card and page padding, or the fullscreen panel padding).
              selectedTaskId
                ? isFullscreen
                  ? "lg:mr-[calc(40vw-1rem)]"
                  : "lg:mr-[calc(40vw-2.5rem)]"
                : ""
            }`}
          >
            <FlowContent
              nodes={nodes}
              edges={edges}
              onSelectTask={setSelectedTaskId}
              isFullscreen={isFullscreen}
              isPreviewOpen={selectedTaskId !== null}
            />
            <GridFullscreenButton isFullscreen={isFullscreen} onToggle={toggleFullscreen} />
          </div>
        </ReactFlowProvider>
      </div>

      <TaskResultPreviewSidebar
        taskId={selectedTaskId}
        onClose={() => setSelectedTaskId(null)}
        showExecutionLink={false}
      />
    </div>
  );
}
