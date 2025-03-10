"use client";

import { useCallback, useState, useMemo } from "react";
import dagre from "dagre";
import {
  ReactFlow,
  Background,
  Controls,
  Node,
  Edge,
  NodeProps,
  Handle,
  Position,
  NodeTypes,
  ReactFlowProvider,
  Panel,
  MarkerType,
} from "@xyflow/react";
import React from "react";
import { TaskFigure } from "@/app/components/TaskFigure";
import JsonView from "react18-json-view";
import "@xyflow/react/dist/style.css";

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
  figurePath?: string[];
  inputParameters?: Record<string, unknown>;
  outputParameters?: Record<string, unknown>;
}

const CustomNode = ({ data }: NodeProps) => {
  const nodeData = data as NodeData;
  return (
    <div
      className="group px-4 shadow-lg rounded-lg border relative transition-colors"
      style={{
        ...getStatusStyles(nodeData.status),
        borderWidth: "2px",
        minWidth: "150px",
        maxWidth: "300px",
        height: "60px", // 固定の高さ
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
      }}
    >
      <Handle type="target" position={Position.Left} />
      <div className="font-semibold truncate">{nodeData.name}</div>
      <div className="text-sm font-medium truncate">{nodeData.status}</div>
      {nodeData.startAt && (
        <div className="tooltip tooltip-bottom absolute -bottom-12 opacity-0 group-hover:opacity-100 transition-opacity bg-base-300 p-2 rounded text-xs whitespace-nowrap z-10">
          <div>Start: {new Date(nodeData.startAt).toLocaleString()}</div>
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

interface TaskDetails {
  name: string;
  status: string;
  startAt?: string;
  elapsedTime?: string;
  figurePath?: string[];
  inputParameters?: Record<string, unknown>;
  outputParameters?: Record<string, unknown>;
}

interface ExecutionDAGProps {
  tasks: TaskNode[];
}

export default function ExecutionDAG({ tasks }: ExecutionDAGProps) {
  const [selectedTask, setSelectedTask] = useState<TaskDetails | null>(null);
  const getLayoutedElements = useCallback(() => {
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
        figurePath: task.figure_path,
        inputParameters: task.input_parameters,
        outputParameters: task.output_parameters,
      },
      width: 180,
      height: 60,
    }));

    const initialEdges: Edge[] = tasks
      .filter(
        (task): task is TaskNode & { upstream_id: string } =>
          typeof task.upstream_id === "string" && task.upstream_id !== ""
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

  const { nodes, edges } = getLayoutedElements();

  return (
    <div className="flex gap-4">
      <ReactFlowProvider>
        <div style={{ width: selectedTask ? "70%" : "100%", height: "400px" }}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            fitView
            className="bg-base-200"
            defaultEdgeOptions={{
              type: "smoothstep",
              animated: true,
              style: { strokeWidth: 2 },
              markerEnd: {
                type: MarkerType.ArrowClosed,
                color: "#64748b",
              },
            }}
            fitViewOptions={{
              padding: 0.2,
            }}
            onNodeClick={(_, node) => {
              const data = node.data as NodeData;
              setSelectedTask({
                name: data.name,
                status: data.status,
                startAt: data.startAt,
                elapsedTime: data.elapsedTime,
                figurePath: data.figurePath,
                inputParameters: data.inputParameters,
                outputParameters: data.outputParameters,
              });
            }}
          >
            <Background />
            <Controls />
            <Panel position="top-left" className="bg-base-100 p-2 rounded">
              <div className="text-sm">Click nodes to see details</div>
            </Panel>
          </ReactFlow>
        </div>
      </ReactFlowProvider>

      {selectedTask && (
        <div
          className="w-[30%] bg-base-100 p-4 rounded-lg shadow overflow-y-auto"
          style={{ height: "600px" }}
        >
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-lg font-semibold">{selectedTask.name}</h3>
            <button
              onClick={() => setSelectedTask(null)}
              className="text-base-content/60 hover:text-base-content"
            >
              ×
            </button>
          </div>

          <div className="space-y-4">
            <div>
              <div className="font-medium">Status</div>
              <div
                className={`text-sm ${
                  selectedTask.status === "running"
                    ? "text-info"
                    : selectedTask.status === "completed"
                    ? "text-success"
                    : selectedTask.status === "scheduled"
                    ? "text-warning"
                    : "text-error"
                }`}
              >
                {selectedTask.status}
              </div>
            </div>

            {selectedTask.startAt && (
              <div>
                <div className="font-medium">Start Time</div>
                <div className="text-sm">
                  {new Date(selectedTask.startAt).toLocaleString()}
                </div>
              </div>
            )}

            {selectedTask.elapsedTime && (
              <div>
                <div className="font-medium">Duration</div>
                <div className="text-sm">{selectedTask.elapsedTime}</div>
              </div>
            )}

            {selectedTask.figurePath && selectedTask.figurePath.length > 0 && (
              <div>
                <div className="font-medium mb-2">Figures</div>
                <div className="space-y-2">
                  <TaskFigure
                    path={selectedTask.figurePath}
                    qid={selectedTask.name}
                    className="w-full h-auto rounded border max-h-[200px] object-contain"
                  />
                </div>
              </div>
            )}

            {selectedTask.inputParameters && (
              <div>
                <div className="font-medium mb-1">Input Parameters</div>
                <div className="bg-base-200 p-2 rounded text-sm">
                  <JsonView
                    src={selectedTask.inputParameters}
                    theme="vscode"
                    collapsed={1}
                  />
                </div>
              </div>
            )}

            {selectedTask.outputParameters && (
              <div>
                <div className="font-medium mb-1">Output Parameters</div>
                <div className="bg-base-200 p-2 rounded text-sm">
                  <JsonView
                    src={selectedTask.outputParameters}
                    theme="vscode"
                    collapsed={1}
                  />
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
