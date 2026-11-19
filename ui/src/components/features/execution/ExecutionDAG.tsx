"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import {
  ReactFlow,
  Background,
  Controls,
  ControlButton,
  Handle,
  Position,
  ReactFlowProvider,
  Panel,
  MarkerType,
  useReactFlow,
} from "@xyflow/react";
import dagre from "dagre";
import { Lock, LockOpen } from "lucide-react";

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

/** Status classes use the theme's semantic colors so nodes stay readable on every theme. */
const getStatusClasses = (status: string): string => {
  switch (status) {
    case "running":
      return "border-info bg-info/10 text-info";
    case "completed":
      return "border-success bg-success/10 text-success";
    case "scheduled":
      return "border-warning bg-warning/10 text-warning";
    case "failed":
      return "border-error bg-error/10 text-error";
    case "cancelled":
      return "border-base-content/40 bg-base-content/5 text-base-content/60";
    default:
      return "border-base-300 bg-base-200 text-base-content/60";
  }
};

/** Edge stroke and arrow follow the theme's content color. */
const EDGE_COLOR = "color-mix(in oklch, var(--color-base-content) 45%, transparent)";

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
      className={`group relative flex h-[60px] min-w-[150px] max-w-[300px] cursor-pointer flex-col justify-center rounded-[var(--radius-field)] border-2 px-4 shadow-xs ${getStatusClasses(
        nodeData.status,
      )} ${nodeData.isSelected ? "ring-2 ring-primary ring-offset-2 ring-offset-base-200" : ""}`}
      aria-current={nodeData.isSelected ? "true" : undefined}
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
 * React Flow canvas for the execution graph. Starts unlocked with pan and zoom enabled;
 * the Controls lock button locks or unlocks pan and zoom. Locking resets the view to the default
 * fitted view and hides the Controls zoom and fit buttons so it stays there. Nodes stay at their
 * computed layout: they cannot be dragged, so dragging on a node pans the canvas.
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
  const [isLocked, setIsLocked] = useState(false);

  // Unlocked, the viewport is the user's pan/zoom: only the locked canvas refits when its
  // container size changes, so the user's view survives fullscreen and preview toggles.
  const isLockedRef = useRef(isLocked);
  useEffect(() => {
    isLockedRef.current = isLocked;
  }, [isLocked]);

  // Fit once on mount, then re-fit the locked canvas whenever fullscreen changes its size.
  // The ref is set when the fit runs so a cancelled frame (Strict Mode re-run) is retried.
  const fittedFullscreen = useRef<boolean | null>(null);
  useEffect(() => {
    if (fittedFullscreen.current === isFullscreen) return;
    if (fittedFullscreen.current !== null && !isLockedRef.current) {
      fittedFullscreen.current = isFullscreen;
      return;
    }
    const frame = requestAnimationFrame(() => {
      fittedFullscreen.current = isFullscreen;
      fitView({ ...FIT_VIEW_OPTIONS, duration: 0 });
    });
    return () => cancelAnimationFrame(frame);
  }, [isFullscreen, fitView]);

  // The canvas gives up width to the preview sidebar with a CSS transition; once that has
  // finished, glide the locked graph into the space that is left. The time the transition settles
  // is kept so that locking mid-transition still fits the final width: the lock button fits the
  // intermediate width at once, and this effect fits again when the transition ends. Unlocking
  // re-runs the effect, so its cleanup cancels a pending fit that would otherwise reset the
  // user's new viewport.
  const previousPreviewOpen = useRef(isPreviewOpen);
  const previewSettlesAt = useRef(0);
  useEffect(() => {
    if (previousPreviewOpen.current !== isPreviewOpen) {
      previousPreviewOpen.current = isPreviewOpen;
      previewSettlesAt.current = Date.now() + PREVIEW_TRANSITION_MS + 50;
    }
    if (!isLocked) return;
    const delay = previewSettlesAt.current - Date.now();
    if (delay <= 0) return;
    const timer = setTimeout(() => {
      fitView({ ...FIT_VIEW_OPTIONS, duration: PREVIEW_TRANSITION_MS });
    }, delay);
    return () => clearTimeout(timer);
  }, [isPreviewOpen, isLocked, fitView]);

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
      nodesDraggable={false}
      nodesConnectable={false}
      elementsSelectable={false}
      defaultEdgeOptions={{
        type: "smoothstep",
        style: { strokeWidth: 2 },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: EDGE_COLOR,
        },
      }}
      fitViewOptions={FIT_VIEW_OPTIONS}
      onNodeClick={(_, node) => onSelectTask(node.id)}
    >
      <Background />
      <Controls
        showInteractive={false}
        showZoom={!isLocked}
        showFitView={!isLocked}
        fitViewOptions={FIT_VIEW_OPTIONS}
      >
        <ControlButton
          onClick={() => {
            if (!isLocked) {
              fitView({ ...FIT_VIEW_OPTIONS, duration: 0 });
            }
            setIsLocked(!isLocked);
          }}
          title={isLocked ? "Unlock view" : "Lock view"}
          aria-label={isLocked ? "Unlock view" : "Lock view"}
        >
          {isLocked ? (
            <Lock size={12} style={{ fill: "none" }} />
          ) : (
            <LockOpen size={12} style={{ fill: "none" }} />
          )}
        </ControlButton>
      </Controls>
      <Panel position="top-left" className="bg-base-100 p-2 rounded flex items-center gap-2">
        <div className="text-sm">Select a node to preview its result</div>
        {!isLocked && (
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
        )}
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
        style: { stroke: EDGE_COLOR, strokeWidth: 2 },
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
