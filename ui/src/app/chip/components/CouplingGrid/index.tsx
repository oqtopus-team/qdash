"use client";

import { useState } from "react";
import { Task } from "@/schemas";
import {
  useFetchLatestCouplingTaskGroupedByChip,
  useFetchHistoricalCouplingTaskGroupedByChip,
} from "@/client/chip/chip";
import { TaskFigure } from "@/app/components/TaskFigure";
import { BsLink } from "react-icons/bs";

interface CouplingGridProps {
  chipId: string;
  selectedTask: string;
  selectedDate: string;
}

interface SelectedTaskInfo {
  path: string;
  couplingId: string;
  task: Task;
}

// Grid configuration
const GRID_SIZE = 8;
const MUX_SIZE = 2; // 2x2 blocks for each mux

export function CouplingGrid({
  chipId,
  selectedTask,
  selectedDate,
}: CouplingGridProps) {
  const [selectedTaskInfo, setSelectedTaskInfo] =
    useState<SelectedTaskInfo | null>(null);

  // Fetch task results
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

  if (isLoadingTask) {
    return (
      <div className="w-full flex justify-center py-12">
        <span className="loading loading-spinner loading-lg"></span>
      </div>
    );
  }

  if (isTaskError) {
    return (
      <div className="alert alert-error">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="stroke-current shrink-0 h-6 w-6"
          fill="none"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="2"
            d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
        <span>Failed to load task data</span>
      </div>
    );
  }

  // Create a mapping of QID to grid position
  const gridPositions: { [key: string]: { row: number; col: number } } = {};
  if (taskResponse?.data?.result) {
    Object.keys(taskResponse.data.result).forEach((qid) => {
      const qidNum = parseInt(qid);
      const muxIndex = Math.floor(qidNum / 4); // Which mux block (0, 1, 2, ...)
      const muxRow = Math.floor(muxIndex / (GRID_SIZE / MUX_SIZE)); // Row of mux blocks
      const muxCol = muxIndex % (GRID_SIZE / MUX_SIZE); // Column of mux blocks
      const localIndex = qidNum % 4; // Position within mux (0-3)
      const localRow = Math.floor(localIndex / 2); // Row within mux (0-1)
      const localCol = localIndex % 2; // Column within mux (0-1)

      gridPositions[qid] = {
        row: muxRow * MUX_SIZE + localRow,
        col: muxCol * MUX_SIZE + localCol,
      };
    });
  }

  // Calculate coupling positions
  const couplingPositions: {
    [key: string]: { row: number; col: number; task: Task };
  } = {};

  if (taskResponse?.data?.result) {
    Object.entries(taskResponse.data.result).forEach(([qid1, task1]) => {
      Object.entries(taskResponse.data.result).forEach(([qid2, _]) => {
        if (qid1 >= qid2) return; // Only process each pair once

        const pos1 = gridPositions[qid1];
        const pos2 = gridPositions[qid2];
        if (!pos1 || !pos2) return;

        // Check if these Couplings are adjacent
        const rowDiff = Math.abs(pos1.row - pos2.row);
        const colDiff = Math.abs(pos1.col - pos2.col);
        if (
          (rowDiff === 1 && colDiff === 0) ||
          (rowDiff === 0 && colDiff === 1)
        ) {
          // Format coupling ID as "0-1" instead of "Q0-Q1"
          const couplingId = `${qid1}-${qid2}`;
          const centerRow = (pos1.row + pos2.row) / 2;
          const centerCol = (pos1.col + pos2.col) / 2;

          // For now, we'll use task1 as the coupling task
          // In a real implementation, you would fetch the actual coupling task
          couplingPositions[couplingId] = {
            row: centerRow,
            col: centerCol,
            task: task1,
          };
        }
      });
    });
  }

  // Get figure path from task
  const getFigurePath = (task: Task): string | null => {
    if (!task.figure_path) return null;
    if (Array.isArray(task.figure_path)) {
      return task.figure_path[0] || null;
    }
    return task.figure_path;
  };

  return (
    <div className="space-y-6">
      {/* Grid Display */}
      <div className="relative grid grid-cols-8 gap-2 p-4 bg-base-200/50 rounded-xl">
        {Array.from({ length: GRID_SIZE * GRID_SIZE }).map((_, index) => {
          const row = Math.floor(index / GRID_SIZE);
          const col = index % GRID_SIZE;

          // Check if this position is a Coupling position
          const qid = Object.keys(gridPositions).find(
            (key) =>
              gridPositions[key].row === row && gridPositions[key].col === col
          );

          if (qid) {
            // Render Coupling cell
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
          } else {
            // Render empty cell
            return (
              <div
                key={index}
                className="aspect-square bg-base-300/50 rounded-lg"
              />
            );
          }
        })}

        {/* Render coupling cells with absolute positioning */}
        {Object.entries(couplingPositions).map(([couplingId, coupling]) => {
          const figurePath = getFigurePath(coupling.task);
          const isHorizontal = Math.abs(coupling.row % 1) < 0.1;
          const top = `${(coupling.row * 100) / (GRID_SIZE - 1)}%`;
          const left = `${(coupling.col * 100) / (GRID_SIZE - 1)}%`;

          return (
            <button
              key={couplingId}
              onClick={() => {
                if (figurePath) {
                  setSelectedTaskInfo({
                    path: figurePath,
                    couplingId,
                    task: coupling.task,
                  });
                }
              }}
              style={{
                position: "absolute",
                top,
                left,
                width: isHorizontal ? "10%" : "5%",
                height: isHorizontal ? "5%" : "10%",
                transform: "translate(-50%, -50%)",
              }}
              className="bg-base-100 rounded-md shadow-sm overflow-hidden hover:shadow-md transition-shadow"
            >
              {coupling.task.figure_path && (
                <div className="absolute inset-0">
                  <TaskFigure
                    path={coupling.task.figure_path}
                    qid={couplingId}
                    className="w-full h-full object-contain"
                  />
                </div>
              )}
              <div className="absolute top-0.5 left-0.5 bg-base-100/80 px-1 py-0.5 rounded text-[10px] font-medium flex items-center gap-0.5">
                <BsLink className="text-[10px]" />
                {couplingId}
              </div>
              <div
                className={`absolute bottom-0.5 right-0.5 w-1.5 h-1.5 rounded-full ${
                  coupling.task.status === "completed"
                    ? "bg-success"
                    : coupling.task.status === "failed"
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
                Result for Coupling {selectedTaskInfo.couplingId}
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
                  path={selectedTaskInfo.path}
                  qid={selectedTaskInfo.couplingId}
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
                        selectedTaskInfo.task.output_parameters
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
