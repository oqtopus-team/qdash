"use client";

import { useState, useEffect } from "react";
import { Task } from "@/schemas";
import {
  useFetchLatestCouplingTaskGroupedByChip,
  useFetchHistoricalCouplingTaskGroupedByChip,
} from "@/client/chip/chip";
import { TaskFigure } from "@/app/components/TaskFigure";

interface CouplingGridProps {
  chipId: string;
  selectedTask: string;
  selectedDate: string;
}

interface SelectedTaskInfo {
  path: string;
  couplingId: string;
  taskList: Task[];
  index: number;
}

const GRID_SIZE = 8;
const MUX_SIZE = 2;

const getCouplingPosition = (qid1: number, qid2: number) => {
  const muxIndex1 = Math.floor(qid1 / 4);
  const muxIndex2 = Math.floor(qid2 / 4);
  const muxRow1 = Math.floor(muxIndex1 / (GRID_SIZE / MUX_SIZE));
  const muxCol1 = muxIndex1 % (GRID_SIZE / MUX_SIZE);
  const muxRow2 = Math.floor(muxIndex2 / (GRID_SIZE / MUX_SIZE));
  const muxCol2 = muxIndex2 % (GRID_SIZE / MUX_SIZE);
  const localIndex1 = qid1 % 4;
  const localIndex2 = qid2 % 4;
  const localRow1 = Math.floor(localIndex1 / 2);
  const localCol1 = localIndex1 % 2;
  const localRow2 = Math.floor(localIndex2 / 2);
  const localCol2 = localIndex2 % 2;

  return {
    row1: muxRow1 * MUX_SIZE + localRow1,
    col1: muxCol1 * MUX_SIZE + localCol1,
    row2: muxRow2 * MUX_SIZE + localRow2,
    col2: muxCol2 * MUX_SIZE + localCol2,
  };
};

export function CouplingGrid({
  chipId,
  selectedTask,
  selectedDate,
}: CouplingGridProps) {
  const [selectedTaskInfo, setSelectedTaskInfo] =
    useState<SelectedTaskInfo | null>(null);
  const [cellSize, setCellSize] = useState(60);

  useEffect(() => {
    const updateSize = () => {
      const vw = window.innerWidth;
      setCellSize(Math.max(Math.floor((vw * 0.75) / GRID_SIZE - 12), 40));
    };
    updateSize();
    window.addEventListener("resize", updateSize);
    return () => window.removeEventListener("resize", updateSize);
  }, []);

  const {
    data: taskResponse,
    isLoading: isLoadingTask,
    isError: isTaskError,
  } = selectedDate === "latest"
    ? useFetchLatestCouplingTaskGroupedByChip(chipId, selectedTask)
    : useFetchHistoricalCouplingTaskGroupedByChip(
        chipId,
        selectedTask,
        selectedDate
      );

  const getFigurePath = (task: Task): string | null => {
    if (!task.figure_path) return null;
    if (Array.isArray(task.figure_path)) return task.figure_path[0] || null;
    return task.figure_path;
  };

  if (isLoadingTask) {
    return (
      <div className="w-full flex justify-center py-12">
        <span className="loading loading-spinner loading-lg"></span>
      </div>
    );
  }
  if (isTaskError) {
    return <div className="alert alert-error">Failed to load task data</div>;
  }

  const normalizedResultMap: Record<string, Task[]> = {};
  if (taskResponse?.data?.result) {
    for (const [couplingId, task] of Object.entries(taskResponse.data.result)) {
      const [a, b] = couplingId.split("-").map(Number);
      const normKey = a < b ? `${a}-${b}` : `${b}-${a}`;
      if (!(normKey in normalizedResultMap)) normalizedResultMap[normKey] = [];
      normalizedResultMap[normKey].push({ ...task, couplingId });
      normalizedResultMap[normKey].sort(
        (a, b) => (b.default_view ? 1 : 0) - (a.default_view ? 1 : 0)
      );
    }
  }

  return (
    <div className="space-y-6 px-4">
      <div className="w-full overflow-x-auto">
        <div
          className="relative inline-block"
          style={{
            width: GRID_SIZE * (cellSize + 8),
            height: GRID_SIZE * (cellSize + 8),
          }}
        >
          {Array.from({ length: GRID_SIZE * GRID_SIZE }).map((_, index) => {
            const muxIndex = Math.floor(index / 4);
            const muxRow = Math.floor(muxIndex / (GRID_SIZE / MUX_SIZE));
            const muxCol = muxIndex % (GRID_SIZE / MUX_SIZE);
            const localIndex = index % 4;
            const localRow = Math.floor(localIndex / 2);
            const localCol = localIndex % 2;
            const row = muxRow * MUX_SIZE + localRow;
            const col = muxCol * MUX_SIZE + localCol;
            const x = col * (cellSize + 8);
            const y = row * (cellSize + 8);
            const qid = muxIndex * 4 + localIndex;

            return (
              <div
                key={qid}
                className="absolute bg-base-300/30 rounded-lg flex items-center justify-center text-sm text-base-content/30"
                style={{ top: y, left: x, width: cellSize, height: cellSize }}
              >
                {qid}
              </div>
            );
          })}

          {Object.entries(normalizedResultMap).map(([normKey, taskList]) => {
            const [qid1, qid2] = normKey.split("-").map(Number);
            const task = taskList[0];
            const figurePath = getFigurePath(task);
            const { row1, col1, row2, col2 } = getCouplingPosition(qid1, qid2);
            const centerX = ((col1 + col2) / 2) * (cellSize + 8) + cellSize / 2;
            const centerY = ((row1 + row2) / 2) * (cellSize + 8) + cellSize / 2;

            return (
              <button
                key={normKey}
                onClick={() => {
                  if (figurePath) {
                    setSelectedTaskInfo({
                      path: figurePath,
                      couplingId: normKey,
                      taskList,
                      index: 0,
                    });
                  }
                }}
                style={{
                  position: "absolute",
                  top: centerY,
                  left: centerX,
                  width: cellSize * 0.6,
                  height: cellSize * 0.6,
                  transform: "translate(-50%, -50%)",
                }}
                className="bg-base-100 rounded-lg shadow-sm overflow-hidden hover:shadow-md transition-shadow"
              >
                {figurePath && (
                  <TaskFigure
                    path={figurePath}
                    qid={task.couplingId}
                    className="w-full h-full object-contain"
                  />
                )}
                <div className="absolute top-1 left-1 bg-base-100/80 px-1.5 py-0.5 rounded text-xs font-medium">
                  {task.couplingId}
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
      </div>

      {selectedTaskInfo && (
        <dialog className="modal modal-open">
          <div className="modal-box max-w-4xl bg-base-100">
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-bold text-lg">
                Result for Coupling{" "}
                {selectedTaskInfo.taskList[selectedTaskInfo.index].couplingId}
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
                <TaskFigure
                  path={
                    selectedTaskInfo.taskList[selectedTaskInfo.index]
                      .figure_path
                  }
                  qid={
                    selectedTaskInfo.taskList[selectedTaskInfo.index].couplingId
                  }
                  className="w-full h-full object-contain"
                />
              </div>
              <div className="space-y-6">
                {selectedTaskInfo.taskList.length > 1 && (
                  <button
                    className="btn btn-sm"
                    onClick={() =>
                      setSelectedTaskInfo((prev) =>
                        prev
                          ? {
                              ...prev,
                              index: (prev.index + 1) % prev.taskList.length,
                            }
                          : null
                      )
                    }
                  >
                    Toggle Direction (
                    {
                      selectedTaskInfo.taskList[selectedTaskInfo.index]
                        .couplingId
                    }
                    )
                  </button>
                )}
                <div className="card bg-base-200 p-4 rounded-xl">
                  <h4 className="font-medium mb-2">Status</h4>
                  <div
                    className={`badge ${
                      selectedTaskInfo.taskList[selectedTaskInfo.index]
                        .status === "completed"
                        ? "badge-success"
                        : selectedTaskInfo.taskList[selectedTaskInfo.index]
                            .status === "failed"
                        ? "badge-error"
                        : "badge-warning"
                    }`}
                  >
                    {selectedTaskInfo.taskList[selectedTaskInfo.index].status}
                  </div>
                </div>
                {selectedTaskInfo.taskList[selectedTaskInfo.index]
                  .output_parameters && (
                  <div className="card bg-base-200 p-4 rounded-xl">
                    <h4 className="font-medium mb-2">Parameters</h4>
                    <div className="space-y-2">
                      {Object.entries(
                        selectedTaskInfo.taskList[selectedTaskInfo.index]
                          .output_parameters
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
                {selectedTaskInfo.taskList[selectedTaskInfo.index].message && (
                  <div className="card bg-base-200 p-4 rounded-xl">
                    <h4 className="font-medium mb-2">Message</h4>
                    <p className="text-sm">
                      {
                        selectedTaskInfo.taskList[selectedTaskInfo.index]
                          .message
                      }
                    </p>
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
