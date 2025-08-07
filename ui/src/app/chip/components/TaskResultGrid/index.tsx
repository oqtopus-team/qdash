"use client";

import React, { useState } from "react";
import { keepPreviousData } from "@tanstack/react-query";
import { Task } from "@/schemas";
import {
  useFetchLatestQubitTaskGroupedByChip,
  useFetchHistoricalQubitTaskGroupedByChip,
  useFetchChipDates,
} from "@/client/chip/chip";
import { TaskFigure } from "@/app/components/TaskFigure";
import dynamic from "next/dynamic";

const PlotlyRenderer = dynamic(
  () => import("@/app/components/PlotlyRenderer").then((mod) => mod.default),
  { ssr: false },
);

interface TaskResultGridProps {
  chipId: string;
  selectedTask: string;
  selectedDate: string;
  gridSize: number;
  onDateChange?: (date: string) => void;
}

interface SelectedTaskInfo {
  qid: string;
  task: Task;
  subIndex?: number;
}

const MUX_SIZE = 2;

export function TaskResultGrid({
  chipId,
  selectedTask,
  selectedDate,
  gridSize,
  onDateChange,
}: TaskResultGridProps) {
  const [selectedTaskInfo, setSelectedTaskInfo] =
    useState<SelectedTaskInfo | null>(null);
  const [viewMode, setViewMode] = useState<"static" | "interactive">("static");

  // Fetch available dates for navigation
  const { data: datesResponse } = useFetchChipDates(chipId, {
    query: {
      enabled: !!chipId,
      staleTime: 300000, // 5 minutes - dates don't change frequently
    },
  });

  // Get available dates for navigation
  const availableDates = React.useMemo(() => {
    const dates = ["latest"];
    if (datesResponse?.data?.data && Array.isArray(datesResponse.data.data)) {
      dates.push(...datesResponse.data.data.sort((a, b) => b.localeCompare(a)));
    }
    return dates;
  }, [datesResponse]);

  // Navigation functions
  const navigateToPreviousDay = () => {
    if (!onDateChange) return;
    
    const currentIndex = availableDates.indexOf(selectedDate);
    if (currentIndex > 0) {
      onDateChange(availableDates[currentIndex - 1]);
    }
  };

  const navigateToNextDay = () => {
    if (!onDateChange) return;
    
    const currentIndex = availableDates.indexOf(selectedDate);
    if (currentIndex < availableDates.length - 1) {
      onDateChange(availableDates[currentIndex + 1]);
    }
  };

  const canNavigatePrevious = availableDates.indexOf(selectedDate) > 0;
  const canNavigateNext = availableDates.indexOf(selectedDate) < availableDates.length - 1;



  const {
    data: taskResponse,
    isLoading: isLoadingTask,
    isError: isTaskError,
  } = selectedDate === "latest"
    ? useFetchLatestQubitTaskGroupedByChip(chipId, selectedTask, {
        query: {
          placeholderData: keepPreviousData,
          staleTime: 30000, // 30 seconds
        },
      })
    : useFetchHistoricalQubitTaskGroupedByChip(
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

  // Update modal data when date changes or new data is fetched
  React.useEffect(() => {
    if (selectedTaskInfo && taskResponse?.data?.result) {
      const updatedTask = taskResponse.data.result[selectedTaskInfo.qid];
      if (updatedTask) {
        setSelectedTaskInfo((prev) =>
          prev ? { ...prev, task: updatedTask } : null
        );
      }
    }
  }, [selectedDate, taskResponse?.data?.result, selectedTaskInfo?.qid]);

  if (isLoadingTask)
    return (
      <div className="w-full flex justify-center py-12">
        <span className="loading loading-spinner loading-lg"></span>
      </div>
    );
  if (isTaskError)
    return <div className="alert alert-error">Failed to load task data</div>;

  const gridPositions: { [key: string]: { row: number; col: number } } = {};
  if (taskResponse?.data?.result) {
    Object.keys(taskResponse.data.result).forEach((qid) => {
      const qidNum = parseInt(qid);
      const muxIndex = Math.floor(qidNum / 4);
      const muxRow = Math.floor(muxIndex / (gridSize / MUX_SIZE));
      const muxCol = muxIndex % (gridSize / MUX_SIZE);
      const localIndex = qidNum % 4;
      const localRow = Math.floor(localIndex / 2);
      const localCol = localIndex % 2;
      gridPositions[qid] = {
        row: muxRow * MUX_SIZE + localRow,
        col: muxCol * MUX_SIZE + localCol,
      };
    });
  }

  const getTaskResult = (qid: string): Task | null =>
    taskResponse?.data?.result?.[qid] || null;

  return (
    <div className="space-y-6">
      <div
        className={`grid gap-2 p-4 bg-base-200/50 rounded-xl`}
        style={{ gridTemplateColumns: `repeat(${gridSize}, minmax(0, 1fr))` }}
      >
        {Array.from({ length: gridSize * gridSize }).map((_, index) => {
          const row = Math.floor(index / gridSize);
          const col = index % gridSize;
          const qid = Object.keys(gridPositions).find(
            (key) =>
              gridPositions[key].row === row && gridPositions[key].col === col,
          );
          if (!qid)
            return (
              <div
                key={index}
                className="aspect-square bg-base-300/50 rounded-lg"
              />
            );

          const task = getTaskResult(qid);
          if (!task)
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

          const figurePath = Array.isArray(task.figure_path)
            ? task.figure_path[0]
            : task.figure_path || null;
          return (
            <button
              key={index}
              onClick={() => {
                if (figurePath) setSelectedTaskInfo({ qid, task, subIndex: 0 });
                setViewMode("static");
              }}
              className={`aspect-square rounded-lg bg-base-100 shadow-sm overflow-hidden hover:shadow-md transition-shadow relative ${
                task.over_threshold
                  ? "border-2 border-primary animate-pulse-light"
                  : ""
              }`}
            >
              {task.figure_path && figurePath && (
                <div className="absolute inset-0">
                  <TaskFigure
                    path={figurePath}
                    qid={qid}
                    className="w-full h-full object-contain"
                  />
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

      {selectedTaskInfo && (
        <dialog className="modal modal-open">
          <div className="modal-box max-w-6xl p-6 rounded-2xl shadow-xl bg-base-100">
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-bold text-lg">
                Result for QID {selectedTaskInfo.qid}
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
                      {selectedDate === "latest" 
                        ? "Latest" 
                        : `${selectedDate.slice(0, 4)}/${selectedDate.slice(4, 6)}/${selectedDate.slice(6, 8)}`
                      }
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

            {viewMode === "static" &&
              (() => {
                const task = selectedTaskInfo.task;
                const figures = Array.isArray(task.figure_path)
                  ? task.figure_path
                  : task.figure_path
                    ? [task.figure_path]
                    : [];
                const currentSubIndex = selectedTaskInfo.subIndex ?? 0;
                const currentFigure = figures[currentSubIndex];
                return (
                  <div className="grid grid-cols-2 gap-8">
                    <div className="aspect-square bg-base-200/50 rounded-xl p-4">
                      {currentFigure && (
                        <TaskFigure
                          path={currentFigure}
                          qid={selectedTaskInfo.qid}
                          className="w-full h-full object-contain"
                        />
                      )}
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
                      {task.json_figure_path && (
                        <button
                          className="btn btn-sm mt-4"
                          onClick={() => setViewMode("interactive")}
                        >
                          Interactive View
                        </button>
                      )}
                    </div>
                    <div className="space-y-6">
                      <div className="card bg-base-200 p-4 rounded-xl">
                        <h4 className="font-medium mb-2">Status</h4>
                        <div
                          className={`badge ${
                            task.status === "completed"
                              ? "badge-success"
                              : task.status === "failed"
                                ? "badge-error"
                                : "badge-warning"
                          }`}
                        >
                          {task.status}
                        </div>
                      </div>
                      {task.output_parameters && (
                        <div className="card bg-base-200 p-4 rounded-xl">
                          <h4 className="font-medium mb-2">Parameters</h4>
                          <div className="space-y-2">
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
                                  <div
                                    key={key}
                                    className="flex justify-between"
                                  >
                                    <span className="font-medium">{key}:</span>
                                    <span>
                                      {typeof paramValue.value === "number"
                                        ? paramValue.value.toFixed(4)
                                        : String(paramValue.value)}
                                      {paramValue.unit
                                        ? ` ${paramValue.unit}`
                                        : ""}
                                    </span>
                                  </div>
                                );
                              },
                            )}
                          </div>
                        </div>
                      )}
                      {task.message && (
                        <div className="card bg-base-200 p-4 rounded-xl">
                          <h4 className="font-medium mb-2">Message</h4>
                          <p className="text-sm">{task.message}</p>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })()}

            {viewMode === "interactive" &&
              selectedTaskInfo.task.json_figure_path &&
              (() => {
                const figures = Array.isArray(
                  selectedTaskInfo.task.json_figure_path,
                )
                  ? selectedTaskInfo.task.json_figure_path
                  : [selectedTaskInfo.task.json_figure_path];
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
                              currentFigure,
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

            <div className="mt-6 flex justify-end gap-2">
              {viewMode === "interactive" && (
                <button
                  className="btn btn-sm"
                  onClick={() => setViewMode("static")}
                >
                  Back to Summary
                </button>
              )}
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
