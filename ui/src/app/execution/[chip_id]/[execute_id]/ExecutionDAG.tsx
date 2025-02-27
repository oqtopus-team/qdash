"use client";

import { useCallback, useState } from "react";
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

const CustomNode = ({ data, selected }: NodeProps) => {
  const nodeData = data as NodeData;
  return (
    <div
      className="group px-4 py-2 shadow-lg rounded-lg border relative transition-colors"
      style={{
        ...getStatusStyles(nodeData.status),
        borderWidth: "2px",
        minWidth: "150px",
      }}
    >
      <Handle type="target" position={Position.Left} />
      <div className="font-semibold">{nodeData.name}</div>
      <div className="text-sm font-medium">{nodeData.status}</div>
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
    const nodes: Node[] = [];
    const edges: Edge[] = [];
    const levelMap = new Map<string, number>();
    const visited = new Set<string>();

    // Calculate levels for each node using DFS
    const calculateLevel = (taskId: string, level: number) => {
      if (visited.has(taskId)) return;
      visited.add(taskId);

      levelMap.set(taskId, Math.max(level, levelMap.get(taskId) || 0));

      // Find children (tasks that have this task as upstream)
      tasks.forEach((task) => {
        if (task.upstream_id === taskId) {
          calculateLevel(task.task_id, level + 1);
        }
      });
    };

    // Find root nodes (tasks with no upstream) and calculate levels
    tasks.forEach((task) => {
      if (task.upstream_id === undefined || task.upstream_id === "") {
        calculateLevel(task.task_id, 0);
      }
    });

    // Create nodes with positions based on levels
    const HORIZONTAL_SPACING = 300;
    const VERTICAL_SPACING = 120;
    const nodesAtLevel = new Map<number, string[]>();

    // First pass: Group nodes by level
    tasks.forEach((task) => {
      const level = levelMap.get(task.task_id) || 0;
      const nodesInLevel = nodesAtLevel.get(level) || [];
      nodesInLevel.push(task.task_id);
      nodesAtLevel.set(level, nodesInLevel);
    });

    // Second pass: Position nodes with vertical centering for each level
    tasks.forEach((task) => {
      const level = levelMap.get(task.task_id) || 0;
      const nodesInLevel = nodesAtLevel.get(level) || [];
      const index = nodesInLevel.indexOf(task.task_id);
      const totalNodesInLevel = nodesInLevel.length;

      // Center nodes vertically within their level
      const verticalCenter = ((totalNodesInLevel - 1) * VERTICAL_SPACING) / 2;
      const yPosition = index * VERTICAL_SPACING - verticalCenter;

      nodes.push({
        id: task.task_id,
        type: "custom",
        position: {
          x: level * HORIZONTAL_SPACING,
          y: yPosition,
        },
        data: {
          name: task.name,
          status: task.status,
          startAt: task.start_at,
          elapsedTime: task.elapsed_time,
          figurePath: task.figure_path,
          inputParameters: task.input_parameters,
          outputParameters: task.output_parameters,
        },
      });

      if (task.upstream_id) {
        edges.push({
          id: `${task.upstream_id}-${task.task_id}`,
          source: task.upstream_id,
          target: task.task_id,
          type: "step",
        });
      }
    });

    return { nodes, edges };
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
              type: "step",
              animated: true,
              style: { strokeWidth: 2 },
              markerEnd: {
                type: MarkerType.ArrowClosed,
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
                  {selectedTask.figurePath.map((path, i) => (
                    <img
                      key={i}
                      src={`http://localhost:5715/executions/figure?path=${encodeURIComponent(
                        path,
                      )}`}
                      alt={`Task Figure ${i + 1}`}
                      className="w-full h-auto rounded border max-h-[200px] object-contain"
                    />
                  ))}
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
