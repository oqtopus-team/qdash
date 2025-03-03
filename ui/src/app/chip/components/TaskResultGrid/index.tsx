"use client";

import { useMemo, useState } from "react";
import { ServerRoutersChipTask } from "@/schemas";
import {
  useFetchChip,
  useFetchLatestTaskGroupedByChip,
} from "@/client/chip/chip";

interface TaskResultGridProps {
  chipId: string;
  selectedTask: string;
}

interface SelectedTaskInfo {
  path: string;
  qid: string;
  task: ServerRoutersChipTask;
}

export function TaskResultGrid({ chipId, selectedTask }: TaskResultGridProps) {
  const [selectedTaskInfo, setSelectedTaskInfo] =
    useState<SelectedTaskInfo | null>(null);

  // For SAMPLE chip, create an 8x8 grid
  const gridSize = 8;
  const muxSize = 2; // 2x2 blocks for each mux

  // Fetch chip data and task results
  const { data: chipResponse } = useFetchChip(chipId);
  const { data: taskResponse } = useFetchLatestTaskGroupedByChip(
    chipId,
    selectedTask,
  );

  // Create a mapping of QID to grid position
  const gridPositions = useMemo(() => {
    const positions: { [key: string]: { row: number; col: number } } = {};
    if (!chipResponse?.data?.qubits) return positions;

    // Calculate positions based on mux layout
    Object.keys(chipResponse.data.qubits).forEach((qid) => {
      const qidNum = parseInt(qid);
      const muxIndex = Math.floor(qidNum / 4); // Which mux block (0, 1, 2, ...)
      const muxRow = Math.floor(muxIndex / (gridSize / muxSize)); // Row of mux blocks
      const muxCol = muxIndex % (gridSize / muxSize); // Column of mux blocks
      const localIndex = qidNum % 4; // Position within mux (0-3)
      const localRow = Math.floor(localIndex / 2); // Row within mux (0-1)
      const localCol = localIndex % 2; // Column within mux (0-1)

      positions[qid] = {
        row: muxRow * muxSize + localRow,
        col: muxCol * muxSize + localCol,
      };
    });

    return positions;
  }, [chipResponse]);

  // Get task result for a specific QID
  const getTaskResult = (qid: string): ServerRoutersChipTask | null => {
    if (!taskResponse?.data?.result?.[qid]) return null;
    return taskResponse.data.result[qid];
  };

  // Get figure path from task
  const getFigurePath = (task: ServerRoutersChipTask): string | null => {
    if (!task.figure_path) return null;
    if (Array.isArray(task.figure_path)) {
      return task.figure_path[0] || null;
    }
    return task.figure_path;
  };

  return (
    <div className="space-y-6">
      {/* Grid Display */}
      <div className="grid grid-cols-8 gap-2 p-4 bg-base-200/50 rounded-xl">
        {Array.from({ length: gridSize * gridSize }).map((_, index) => {
          const row = Math.floor(index / gridSize);
          const col = index % gridSize;
          const qid = Object.keys(gridPositions).find(
            (key) =>
              gridPositions[key].row === row && gridPositions[key].col === col,
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

          const figurePath = getFigurePath(task);

          return (
            <button
              key={index}
              onClick={() => {
                if (figurePath) {
                  setSelectedTaskInfo({
                    path: figurePath,
                    qid,
                    task,
                  });
                }
              }}
              className="aspect-square bg-base-100 rounded-lg shadow-sm overflow-hidden hover:shadow-md transition-shadow relative"
            >
              {task.figure_path && (
                <div className="absolute inset-0">
                  {Array.isArray(task.figure_path) ? (
                    task.figure_path.map((path, i) => (
                      <img
                        key={i}
                        src={`http://localhost:5715/executions/figure?path=${encodeURIComponent(
                          path,
                        )}`}
                        alt={`Result for QID ${qid}`}
                        className="w-full h-full object-contain"
                      />
                    ))
                  ) : (
                    <img
                      src={`http://localhost:5715/executions/figure?path=${encodeURIComponent(
                        task.figure_path,
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
            </button>
          );
        })}
      </div>

      {/* Task Result Modal */}
      {selectedTaskInfo && (
        <dialog className="modal modal-open">
          <div className="modal-box max-w-4xl bg-base-100">
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-bold text-lg">
                Result for QID {selectedTaskInfo.qid}
              </h3>
              <button
                onClick={() => setSelectedTaskInfo(null)}
                className="btn btn-sm btn-circle btn-ghost"
              >
                ✕
              </button>
            </div>
            <div className="grid grid-cols-2 gap-8">
              <div className="aspect-square bg-base-200/50 rounded-xl p-4">
                <img
                  src={`http://localhost:5715/executions/figure?path=${encodeURIComponent(
                    selectedTaskInfo.path,
                  )}`}
                  alt={`Result for QID ${selectedTaskInfo.qid}`}
                  className="w-full h-full object-contain"
                />
              </div>
              <div className="space-y-6">
                <div className="card bg-base-200 p-4 rounded-xl">
                  <h4 className="font-medium mb-2">Status</h4>
                  <div
                    className={`badge ${
                      selectedTaskInfo.task.status === "completed"
                        ? "badge-success"
                        : selectedTaskInfo.task.status === "failed"
                          ? "badge-error"
                          : "badge-warning"
                    }`}
                  >
                    {selectedTaskInfo.task.status}
                  </div>
                </div>
                {selectedTaskInfo.task.output_parameters && (
                  <div className="card bg-base-200 p-4 rounded-xl">
                    <h4 className="font-medium mb-2">Parameters</h4>
                    <div className="space-y-2">
                      {Object.entries(
                        selectedTaskInfo.task.output_parameters,
                      ).map(([key, value]) => {
                        const paramValue = (
                          typeof value === "object" &&
                          value !== null &&
                          "value" in value
                            ? value
                            : { value }
                        ) as { value: number | string; unit?: string };
                        return (
                          <div key={key} className="flex justify-between">
                            <span className="font-medium">{key}:</span>
                            <span>
                              {typeof paramValue.value === "number"
                                ? paramValue.value.toFixed(4)
                                : String(paramValue.value)}
                              {paramValue.unit ? ` ${paramValue.unit}` : ""}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
                {selectedTaskInfo.task.message && (
                  <div className="card bg-base-200 p-4 rounded-xl">
                    <h4 className="font-medium mb-2">Message</h4>
                    <p className="text-sm">{selectedTaskInfo.task.message}</p>
                  </div>
                )}
              </div>
            </div>
          </div>
          <form method="dialog" className="modal-backdrop">
            <button onClick={() => setSelectedTaskInfo(null)}>close</button>
          </form>
        </dialog>
      )}
    </div>
  );
}
