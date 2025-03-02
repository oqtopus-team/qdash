"use client";

import { useMemo } from "react";
import { ServerRoutersChipTask } from "@/schemas";

interface GridViewProps {
  chipData: any;
  selectedTask: string;
  tasks: string[];
  onTaskChange: (task: string) => void;
}

export function GridView({
  chipData,
  selectedTask,
  tasks,
  onTaskChange,
}: GridViewProps) {
  // For SAMPLE chip, create an 8x8 grid
  const gridSize = 8;

  // Create a mapping of QID to grid position
  const gridPositions = useMemo(() => {
    const positions: { [key: string]: { row: number; col: number } } = {};
    if (!chipData?.qubits) return positions;

    Object.keys(chipData.qubits).forEach((qid) => {
      const qidNum = parseInt(qid);
      positions[qid] = {
        row: Math.floor(qidNum / gridSize),
        col: qidNum % gridSize,
      };
    });

    return positions;
  }, [chipData]);

  // Get task result for a specific QID
  const getTaskResult = (qid: string): ServerRoutersChipTask | null => {
    const qubit = chipData?.qubits?.[qid];
    if (!qubit?.data?.[selectedTask]) return null;

    const task = qubit.data[selectedTask];
    if (task.status !== "completed" && task.status !== "failed") return null;
    return task as ServerRoutersChipTask;
  };

  return (
    <div className="space-y-6">
      {/* Task Selection */}
      <div className="flex justify-between items-center">
        <div className="flex items-center gap-4">
          <h3 className="text-lg font-medium">Task:</h3>
          <select
            className="select select-bordered w-64"
            value={selectedTask}
            onChange={(e) => onTaskChange(e.target.value)}
          >
            <option value="">Select task</option>
            {tasks.map((task) => (
              <option key={task} value={task}>
                {task}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Grid Display */}
      <div className="grid grid-cols-8 gap-2 p-4 bg-base-200/50 rounded-xl">
        {Array.from({ length: gridSize * gridSize }).map((_, index) => {
          const row = Math.floor(index / gridSize);
          const col = index % gridSize;
          const qid = Object.keys(gridPositions).find(
            (key) =>
              gridPositions[key].row === row && gridPositions[key].col === col
          );

          if (!qid) {
            return (
              <div
                key={index}
                className="aspect-square bg-base-300/50 rounded-lg"
              />
            );
          }

          const task = getTaskResult(qid);
          if (!task) {
            return (
              <div
                key={index}
                className="aspect-square bg-base-300 rounded-lg flex items-center justify-center"
              >
                <div className="text-sm font-medium text-base-content/50">
                  {qid}
                </div>
              </div>
            );
          }

          return (
            <div
              key={index}
              className="aspect-square bg-base-100 rounded-lg shadow-sm overflow-hidden hover:shadow-md transition-shadow relative group"
            >
              {task.figure_path && (
                <div className="absolute inset-0">
                  {Array.isArray(task.figure_path) ? (
                    task.figure_path.map((path, i) => (
                      <img
                        key={i}
                        src={`http://localhost:5715/executions/figure?path=${encodeURIComponent(
                          path
                        )}`}
                        alt={`Result for QID ${qid}`}
                        className="w-full h-full object-contain"
                      />
                    ))
                  ) : (
                    <img
                      src={`http://localhost:5715/executions/figure?path=${encodeURIComponent(
                        task.figure_path
                      )}`}
                      alt={`Result for QID ${qid}`}
                      className="w-full h-full object-contain"
                    />
                  )}
                </div>
              )}
              <div className="absolute top-1 left-1 bg-base-100/80 px-1.5 py-0.5 rounded text-xs font-medium">
                {qid}
              </div>
              <div
                className={`absolute bottom-1 right-1 w-2 h-2 rounded-full ${
                  task.status === "completed"
                    ? "bg-success"
                    : task.status === "failed"
                    ? "bg-error"
                    : "bg-warning"
                }`}
              />
              {task.output_parameters && (
                <div className="absolute inset-0 bg-base-100/90 opacity-0 group-hover:opacity-100 transition-opacity p-2">
                  <div className="text-xs overflow-y-auto h-full">
                    {Object.entries(task.output_parameters).map(
                      ([key, value]) => {
                        const paramValue = (
                          typeof value === "object" &&
                          value !== null &&
                          "value" in value
                            ? value
                            : { value }
                        ) as { value: number | string; unit?: string };
                        return (
                          <div key={key} className="mb-1">
                            <span className="font-medium">{key}:</span>{" "}
                            {typeof paramValue.value === "number"
                              ? paramValue.value.toFixed(4)
                              : String(paramValue.value)}
                            {paramValue.unit ? ` ${paramValue.unit}` : ""}
                          </div>
                        );
                      }
                    )}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
