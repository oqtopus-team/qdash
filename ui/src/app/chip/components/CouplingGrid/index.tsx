"use client";

import dynamic from "next/dynamic";
import { useState, useEffect, useCallback } from "react";

import { keepPreviousData } from "@tanstack/react-query";

import type { Task } from "@/schemas";

import { TaskFigure } from "@/app/components/TaskFigure";
import { useDateNavigation } from "@/app/hooks/useDateNavigation";
import {
  useFetchLatestCouplingTaskGroupedByChip,
  useFetchHistoricalCouplingTaskGroupedByChip,
} from "@/client/chip/chip";

const PlotlyRenderer = dynamic(
  () => import("@/app/components/PlotlyRenderer").then((mod) => mod.default),
  { ssr: false },
);

interface CouplingGridProps {
  chipId: string;
  selectedTask: string;
  selectedDate: string;
  gridSize: number;
  onDateChange?: (date: string) => void;
}

interface ParameterValue {
  value: unknown;
  unit?: string;
}

interface ExtendedTask extends Task {
  couplingId: string;
}

interface SelectedTaskInfo {
  path: string;
  couplingId: string;
  taskList: ExtendedTask[];
  index: number;
  subIndex?: number;
}

const MUX_SIZE = 2;

const getCouplingPosition = (qid1: number, qid2: number, gridSize: number) => {
  const muxIndex1 = Math.floor(qid1 / 4);
  const muxIndex2 = Math.floor(qid2 / 4);
  const muxRow1 = Math.floor(muxIndex1 / (gridSize / MUX_SIZE));
  const muxCol1 = muxIndex1 % (gridSize / MUX_SIZE);
  const muxRow2 = Math.floor(muxIndex2 / (gridSize / MUX_SIZE));
  const muxCol2 = muxIndex2 % (gridSize / MUX_SIZE);
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
  gridSize,
  onDateChange,
}: CouplingGridProps) {
  const [selectedTaskInfo, setSelectedTaskInfo] =
    useState<SelectedTaskInfo | null>(null);
  const [viewMode, setViewMode] = useState<"static" | "interactive">("static");
  const [cellSize, setCellSize] = useState(60);

  // Track previous date to distinguish modal navigation from external navigation
  const [previousDate, setPreviousDate] = useState(selectedDate);

  // Use custom hook for date navigation
  const {
    navigateToPreviousDay: originalNavigateToPreviousDay,
    navigateToNextDay: originalNavigateToNextDay,
    canNavigatePrevious,
    canNavigateNext,
    formatDate,
  } = useDateNavigation(chipId, selectedDate, onDateChange);

  // Wrap navigation functions to track modal navigation
  const navigateToPreviousDay = useCallback(() => {
    if (selectedTaskInfo) {
      // Modal navigation - don't close modal
      originalNavigateToPreviousDay();
    } else {
      originalNavigateToPreviousDay();
    }
  }, [originalNavigateToPreviousDay, selectedTaskInfo]);

  const navigateToNextDay = useCallback(() => {
    if (selectedTaskInfo) {
      // Modal navigation - don't close modal
      originalNavigateToNextDay();
    } else {
      originalNavigateToNextDay();
    }
  }, [originalNavigateToNextDay, selectedTaskInfo]);

  useEffect(() => {
    const updateSize = () => {
      const vw = window.innerWidth;
      setCellSize(Math.max(Math.floor((vw * 0.75) / gridSize - 12), 30));
    };
    updateSize();
    window.addEventListener("resize", updateSize);
    return () => window.removeEventListener("resize", updateSize);
  }, [gridSize]);

  const {
    data: taskResponse,
    isLoading,
    isError,
  } = selectedDate === "latest"
    ? useFetchLatestCouplingTaskGroupedByChip(chipId, selectedTask, {
        query: {
          placeholderData: keepPreviousData,
          staleTime: 30000, // 30 seconds
        },
      })
    : useFetchHistoricalCouplingTaskGroupedByChip(
        chipId,
        selectedTask,
        selectedDate,
        {
          query: {
            placeholderData: keepPreviousData,
            staleTime: 30000, // 30 seconds
          },
        },
      );

  // Reset modal only when date changes externally (not from modal navigation)
  useEffect(() => {
    if (previousDate !== selectedDate && !selectedTaskInfo) {
      // External navigation - no modal open, safe to update
      setPreviousDate(selectedDate);
    } else if (previousDate !== selectedDate && selectedTaskInfo) {
      // Date changed while modal is open - update previous date but keep modal
      setPreviousDate(selectedDate);
    }
  }, [selectedDate, selectedTaskInfo, previousDate]);

  // Update modal data with debounce to prevent race conditions
  useEffect(() => {
    let timeoutId: NodeJS.Timeout;

    if (selectedTaskInfo && taskResponse?.data?.result) {
      timeoutId = setTimeout(() => {
        const normalizedResultMap: Record<string, ExtendedTask[]> = {};
        for (const [couplingId, task] of Object.entries(
          taskResponse.data.result,
        )) {
          const [a, b] = couplingId.split("-").map(Number);
          const normKey = a < b ? `${a}-${b}` : `${b}-${a}`;
          if (!normalizedResultMap[normKey]) normalizedResultMap[normKey] = [];
          normalizedResultMap[normKey].push({
            ...task,
            couplingId,
          } as ExtendedTask);
          normalizedResultMap[normKey].sort(
            (a, b) => (b.default_view ? 1 : 0) - (a.default_view ? 1 : 0),
          );
        }

        const updatedTaskList =
          normalizedResultMap[selectedTaskInfo.couplingId];
        if (updatedTaskList) {
          setSelectedTaskInfo((prev) => {
            // Only update if the modal is still open and for the same couplingId
            if (prev?.couplingId === selectedTaskInfo.couplingId) {
              return { ...prev, taskList: updatedTaskList };
            }
            return prev;
          });
        }
      }, 100); // 100ms debounce
    }

    return () => {
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    };
  }, [taskResponse?.data?.result, selectedTaskInfo?.couplingId]);

  const normalizedResultMap: Record<string, ExtendedTask[]> = {};
  if (taskResponse?.data?.result) {
    for (const [couplingId, task] of Object.entries(taskResponse.data.result)) {
      const [a, b] = couplingId.split("-").map(Number);
      const normKey = a < b ? `${a}-${b}` : `${b}-${a}`;
      if (!normalizedResultMap[normKey]) normalizedResultMap[normKey] = [];
      normalizedResultMap[normKey].push({
        ...task,
        couplingId,
      } as ExtendedTask);
      normalizedResultMap[normKey].sort(
        (a, b) => (b.default_view ? 1 : 0) - (a.default_view ? 1 : 0),
      );
    }
  }

  if (isLoading)
    return (
      <div className="w-full flex justify-center py-12">
        <span className="loading loading-spinner loading-lg"></span>
      </div>
    );
  if (isError)
    return <div className="alert alert-error">Failed to load data</div>;

  return (
    <div className="space-y-6 px-4">
      <div className="w-full overflow-x-auto">
        <div
          className="relative inline-block"
          style={{
            width: gridSize * (cellSize + 8),
            height: gridSize * (cellSize + 8),
          }}
        >
          {Array.from({ length: gridSize === 8 ? 64 : 144 }).map((_, qid) => {
            const muxIndex = Math.floor(qid / 4);
            const localIndex = qid % 4;
            const muxRow = Math.floor(muxIndex / (gridSize / MUX_SIZE));
            const muxCol = muxIndex % (gridSize / MUX_SIZE);
            const localRow = Math.floor(localIndex / 2);
            const localCol = localIndex % 2;
            const row = muxRow * MUX_SIZE + localRow;
            const col = muxCol * MUX_SIZE + localCol;
            const x = col * (cellSize + 8);
            const y = row * (cellSize + 8);
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
            const figurePath = Array.isArray(task.figure_path)
              ? task.figure_path[0]
              : task.figure_path || null;
            const { row1, col1, row2, col2 } = getCouplingPosition(
              qid1,
              qid2,
              gridSize,
            );
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
                      subIndex: 0,
                    });
                    setViewMode("static");
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
                className={`rounded-lg bg-base-100 shadow-sm overflow-hidden hover:shadow-md transition-shadow ${
                  task.over_threshold
                    ? "border-2 border-primary animate-pulse-light"
                    : ""
                }`}
              >
                {figurePath && (
                  <TaskFigure
                    path={figurePath}
                    qid={String(task.couplingId)}
                    className="w-full h-full object-contain"
                  />
                )}
              </button>
            );
          })}
        </div>
      </div>

      {selectedTaskInfo && (
        <dialog className="modal modal-open">
          <div className="modal-box max-w-6xl p-6 rounded-2xl shadow-xl bg-base-100">
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-bold text-lg">
                Coupling{" "}
                {selectedTaskInfo.taskList[selectedTaskInfo.index].couplingId}
              </h3>
              <div className="flex items-center gap-2">
                {onDateChange && (
                  <>
                    <button
                      onClick={navigateToPreviousDay}
                      disabled={!canNavigatePrevious}
                      className="btn btn-sm btn-ghost"
                      title="Previous Day"
                    >
                      ←
                    </button>
                    <span className="text-sm text-base-content/70 px-2">
                      {formatDate(selectedDate)}
                    </span>
                    <button
                      onClick={navigateToNextDay}
                      disabled={!canNavigateNext}
                      className="btn btn-sm btn-ghost"
                      title="Next Day"
                    >
                      →
                    </button>
                  </>
                )}
                <button
                  onClick={() => setSelectedTaskInfo(null)}
                  className="btn btn-sm btn-circle btn-ghost"
                >
                  ✕
                </button>
              </div>
            </div>

            {viewMode === "static" ? (
              <div className="grid grid-cols-2 gap-8">
                <div className="aspect-square bg-base-200/50 rounded-xl p-4">
                  {(() => {
                    const selectedTask =
                      selectedTaskInfo.taskList[selectedTaskInfo.index];
                    const figures = Array.isArray(selectedTask.figure_path)
                      ? selectedTask.figure_path
                      : selectedTask.figure_path
                        ? [selectedTask.figure_path]
                        : [];
                    const currentSubIndex = selectedTaskInfo.subIndex ?? 0;
                    const currentFigure = figures[currentSubIndex];
                    return (
                      <>
                        <TaskFigure
                          path={currentFigure}
                          qid={String(selectedTask.couplingId)}
                          className="w-full h-full object-contain"
                        />
                        {figures.length > 1 && (
                          <div className="flex justify-center mt-2 gap-2">
                            <button
                              className="btn btn-xs"
                              onClick={() =>
                                setSelectedTaskInfo((prev) =>
                                  prev
                                    ? {
                                        ...prev,
                                        subIndex:
                                          ((prev.subIndex ?? 0) -
                                            1 +
                                            figures.length) %
                                          figures.length,
                                      }
                                    : null,
                                )
                              }
                            >
                              ◀
                            </button>
                            <span className="text-sm">
                              {currentSubIndex + 1} / {figures.length}
                            </span>
                            <button
                              className="btn btn-xs"
                              onClick={() =>
                                setSelectedTaskInfo((prev) =>
                                  prev
                                    ? {
                                        ...prev,
                                        subIndex:
                                          ((prev.subIndex ?? 0) + 1) %
                                          figures.length,
                                      }
                                    : null,
                                )
                              }
                            >
                              ▶
                            </button>
                          </div>
                        )}
                        {selectedTask.json_figure_path && (
                          <button
                            className="btn btn-sm mt-4"
                            onClick={() => setViewMode("interactive")}
                          >
                            Interactive View
                          </button>
                        )}
                      </>
                    );
                  })()}
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
                                subIndex: 0,
                              }
                            : null,
                        )
                      }
                    >
                      Toggle Direction
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
                  {(() => {
                    const outputParams =
                      selectedTaskInfo.taskList[selectedTaskInfo.index]
                        .output_parameters;
                    if (!outputParams) return null;

                    return (
                      <div className="card bg-base-200 p-4 rounded-xl">
                        <h4 className="font-medium mb-2">Parameters</h4>
                        <div className="space-y-2">
                          {Object.entries(outputParams).map(([key, value]) => {
                            const paramValue: ParameterValue =
                              typeof value === "object" &&
                              value !== null &&
                              "value" in value
                                ? (value as ParameterValue)
                                : { value };
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
                    );
                  })()}
                  {selectedTaskInfo.taskList[selectedTaskInfo.index]
                    .message && (
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
            ) : (
              <div className="w-full h-[70vh] flex justify-center items-center">
                <div className="w-[70vw] h-full bg-base-200 rounded-xl p-4 shadow flex justify-center items-center">
                  <div className="w-full h-full flex justify-center items-center">
                    <div className="w-fit h-fit m-auto">
                      <PlotlyRenderer
                        className="w-full h-full"
                        fullPath={`${
                          process.env.NEXT_PUBLIC_API_URL
                        }/api/executions/figure?path=${encodeURIComponent(
                          selectedTaskInfo.taskList[selectedTaskInfo.index]
                            .json_figure_path?.[0] || "",
                        )}`}
                      />
                    </div>
                  </div>
                </div>
              </div>
            )}

            <div className="mt-6 flex justify-end gap-2">
              {viewMode === "interactive" &&
                (() => {
                  const selectedTask =
                    selectedTaskInfo.taskList[selectedTaskInfo.index];
                  const path = selectedTask.json_figure_path;
                  const figures = Array.isArray(path)
                    ? path
                    : path
                      ? [path]
                      : [];
                  const currentSubIndex = selectedTaskInfo.subIndex ?? 0;
                  const currentFigure = figures[currentSubIndex];

                  return (
                    <div className="w-full h-[70vh] flex flex-col justify-center items-center space-y-4">
                      <div className="w-[70vw] h-full bg-base-200 rounded-xl p-4 shadow flex justify-center items-center">
                        <div className="w-full h-full flex justify-center items-center">
                          <div className="w-fit h-fit m-auto">
                            <PlotlyRenderer
                              className="w-full h-full"
                              fullPath={`${
                                process.env.NEXT_PUBLIC_API_URL
                              }/api/executions/figure?path=${encodeURIComponent(
                                currentFigure || "",
                              )}`}
                            />
                          </div>
                        </div>
                      </div>

                      {figures.length > 1 && (
                        <div className="flex justify-center gap-2">
                          <button
                            className="btn btn-xs"
                            onClick={() =>
                              setSelectedTaskInfo((prev) =>
                                prev
                                  ? {
                                      ...prev,
                                      subIndex:
                                        ((prev.subIndex ?? 0) -
                                          1 +
                                          figures.length) %
                                        figures.length,
                                    }
                                  : null,
                              )
                            }
                          >
                            ◀
                          </button>
                          <span className="text-sm">
                            {currentSubIndex + 1} / {figures.length}
                          </span>
                          <button
                            className="btn btn-xs"
                            onClick={() =>
                              setSelectedTaskInfo((prev) =>
                                prev
                                  ? {
                                      ...prev,
                                      subIndex:
                                        ((prev.subIndex ?? 0) + 1) %
                                        figures.length,
                                    }
                                  : null,
                              )
                            }
                          >
                            ▶
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })()}
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
