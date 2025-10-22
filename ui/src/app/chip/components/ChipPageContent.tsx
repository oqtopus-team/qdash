"use client";

import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import React, { useState, useEffect } from "react";

import { keepPreviousData } from "@tanstack/react-query";
import { BsGrid, BsListUl } from "react-icons/bs";

import { CouplingGrid } from "./CouplingGrid";
import { TaskResultGrid } from "./TaskResultGrid";

import type { Task, MuxDetailResponseDetail, TaskResponse } from "@/schemas";

import { ChipSelector } from "@/app/components/ChipSelector";
import { DateSelector } from "@/app/components/DateSelector";
import { TaskFigure } from "@/app/components/TaskFigure";
import { TaskSelector } from "@/app/components/TaskSelector";
import { useDateNavigation } from "@/app/hooks/useDateNavigation";
import { useChipUrlState } from "@/app/hooks/useUrlState";
import { useListMuxes, useFetchChip, useListChips } from "@/client/chip/chip";
import { useFetchAllTasks } from "@/client/task/task";

const PlotlyRenderer = dynamic(
  () => import("@/app/components/PlotlyRenderer").then((mod) => mod.default),
  { ssr: false },
);

interface SelectedTaskInfo {
  qid: string;
  task: Task;
  subIndex?: number;
}

export function ChipPageContent() {
  const router = useRouter();
  // URL state management
  const {
    selectedChip,
    selectedDate,
    selectedTask,
    viewMode,
    setSelectedChip,
    setSelectedDate,
    setSelectedTask,
    setViewMode,
    isInitialized,
  } = useChipUrlState();

  const [gridSize, setGridSize] = useState<number>(8);

  const { data: chipData } = useFetchChip(selectedChip);
  const { data: chipsData } = useListChips();

  // Set default chip only when URL is initialized and no chip is selected from URL
  useEffect(() => {
    if (
      isInitialized &&
      !selectedChip &&
      chipsData?.data &&
      chipsData.data.length > 0
    ) {
      // Sort chips by installation date and select the most recent one
      const sortedChips = [...chipsData.data].sort((a, b) => {
        const dateA = a.installed_at ? new Date(a.installed_at).getTime() : 0;
        const dateB = b.installed_at ? new Date(b.installed_at).getTime() : 0;
        return dateB - dateA;
      });
      setSelectedChip(sortedChips[0].chip_id);
    }
  }, [isInitialized, selectedChip, chipsData, setSelectedChip]);

  useEffect(() => {
    if (chipData?.data?.size) {
      setGridSize(Math.sqrt(chipData.data.size));
    }
  }, [chipData?.data?.size]);
  const [expandedMuxes, setExpandedMuxes] = useState<{
    [key: string]: boolean;
  }>({});
  const [selectedTaskInfo, setSelectedTaskInfo] =
    useState<SelectedTaskInfo | null>(null);
  const [modalViewMode, setModalViewMode] = useState<"static" | "interactive">("static");

  // Track previous date to distinguish modal navigation from external navigation
  const [previousDate, setPreviousDate] = useState(selectedDate);

  const { data: tasks } = useFetchAllTasks();

  // Use custom hook for date navigation
  const {
    navigateToPreviousDay: originalNavigateToPreviousDay,
    navigateToNextDay: originalNavigateToNextDay,
    canNavigatePrevious,
    canNavigateNext,
    formatDate,
  } = useDateNavigation(selectedChip, selectedDate, setSelectedDate);

  // Navigation functions - modal state is tracked elsewhere, these just navigate
  const navigateToPreviousDay = originalNavigateToPreviousDay;
  const navigateToNextDay = originalNavigateToNextDay;

  // Update selected task when view mode changes only if no task is selected from URL
  useEffect(() => {
    if (!isInitialized) return; // Wait for URL state to be initialized

    // Only set defaults if no task is selected or if the current task doesn't match the view mode
    if (viewMode === "2q" && tasks?.data?.tasks) {
      const availableTasks = tasks.data.tasks.filter(
        (task: TaskResponse) => task.task_type === "coupling",
      );
      // Check if current task is valid for 2q view
      const currentTaskValid = availableTasks.some(
        (task: TaskResponse) => task.name === selectedTask,
      );

      if (!currentTaskValid) {
        const checkBellState = availableTasks.find(
          (task: TaskResponse) => task.name === "CheckBellState",
        );
        if (checkBellState) {
          setSelectedTask("CheckBellState");
        } else if (availableTasks.length > 0) {
          setSelectedTask(availableTasks[0].name);
        }
      }
    } else if (viewMode === "1q" && tasks?.data?.tasks) {
      const availableTasks = tasks.data.tasks.filter(
        (task: TaskResponse) => task.task_type === "qubit",
      );
      // Check if current task is valid for 1q view
      const currentTaskValid = availableTasks.some(
        (task: TaskResponse) => task.name === selectedTask,
      );

      if (!currentTaskValid && !selectedTask) {
        // Only set default if no task is selected
        setSelectedTask("CheckRabi");
      }
    }
  }, [
    viewMode,
    tasks?.data?.tasks,
    isInitialized,
    selectedTask,
    setSelectedTask,
  ]);
  const {
    data: muxData,
    isLoading: isLoadingMux,
    isError: isMuxError,
  } = useListMuxes(selectedChip || "", {
    query: {
      placeholderData: keepPreviousData,
      staleTime: 30000, // 30 seconds
    },
  });

  // Reset modal only when date changes externally (not from modal navigation)
  React.useEffect(() => {
    if (previousDate !== selectedDate && !selectedTaskInfo) {
      // External navigation - no modal open, safe to update
      setPreviousDate(selectedDate);
    } else if (previousDate !== selectedDate && selectedTaskInfo) {
      // Date changed while modal is open - update previous date but keep modal
      setPreviousDate(selectedDate);
    }
  }, [selectedDate, selectedTaskInfo, previousDate]);

  // Update modal data with debounce to prevent race conditions
  React.useEffect(() => {
    let timeoutId: NodeJS.Timeout;

    if (selectedTaskInfo && muxData?.data) {
      timeoutId = setTimeout(() => {
        // Find the updated task from mux data
        let foundTask: Task | null = null;
        Object.values(muxData.data.muxes).forEach((muxDetail) => {
          Object.values(muxDetail.detail).forEach((tasksByName) => {
            Object.values(tasksByName as { [key: string]: Task }).forEach(
              (task) => {
                if (task.qid === selectedTaskInfo.qid && task.figure_path) {
                  foundTask = task;
                }
              },
            );
          });
        });

        if (foundTask) {
          const figurePath = Array.isArray((foundTask as Task).figure_path)
            ? ((foundTask as Task).figure_path as string[])[0]
            : (foundTask as Task).figure_path || null;

          if (figurePath && typeof figurePath === "string") {
            setSelectedTaskInfo((prev) => {
              // Only update if the modal is still open and for the same qid
              if (prev?.qid === selectedTaskInfo.qid) {
                return { ...prev, path: figurePath, task: foundTask! };
              }
              return prev;
            });
          }
        }
      }, 100); // 100ms debounce
    }

    return () => {
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    };
  }, [muxData?.data, selectedTaskInfo?.qid]);

  // Get all QIDs for this mux (always 4 qids based on mux number)
  const getQidsForMux = (muxNum: number): string[] => {
    const startQid = muxNum * 4;
    return [
      String(startQid),
      String(startQid + 1),
      String(startQid + 2),
      String(startQid + 3),
    ];
  };

  // Group tasks by name for each mux
  const getTaskGroups = (detail: MuxDetailResponseDetail) => {
    const taskGroups: {
      [key: string]: { [key: string]: Task };
    } = {};

    // Iterate through each QID in the mux detail
    Object.entries(detail).forEach(([qid, tasksByName]) => {
      // Iterate through each task
      Object.entries(tasksByName as { [key: string]: Task }).forEach(
        ([taskName, task]) => {
          if (task.status !== "completed" && task.status !== "failed") return;

          if (!taskGroups[taskName]) {
            taskGroups[taskName] = {};
          }
          taskGroups[taskName][qid] = task;
        },
      );
    });

    return taskGroups;
  };

  // Get latest update time info from tasks
  const getLatestUpdateInfo = (
    detail: MuxDetailResponseDetail,
  ): { time: Date; isRecent: boolean } => {
    let latestTime = new Date(0);

    Object.values(detail).forEach((tasksByName) => {
      Object.values(tasksByName as { [key: string]: Task }).forEach((task) => {
        if (task.end_at) {
          const taskEndTime = new Date(task.end_at);
          if (taskEndTime > latestTime) {
            latestTime = taskEndTime;
          }
        }
      });
    });

    const now = new Date();
    const isRecent = now.getTime() - latestTime.getTime() < 24 * 60 * 60 * 1000;

    return { time: latestTime, isRecent };
  };

  // Format relative time
  const formatRelativeTime = (date: Date): string => {
    const now = new Date();
    const diffInSeconds = Math.floor((now.getTime() - date.getTime()) / 1000);

    if (diffInSeconds < 60) return "just now";
    if (diffInSeconds < 3600) return `${Math.floor(diffInSeconds / 60)}m ago`;
    if (diffInSeconds < 86400)
      return `${Math.floor(diffInSeconds / 3600)}h ago`;
    return date.toLocaleString();
  };

  // Get figure path from task
  const getFigurePath = (task: Task): string | null => {
    if (!task.figure_path) return null;
    if (Array.isArray(task.figure_path)) {
      return task.figure_path[0] || null;
    }
    return task.figure_path;
  };

  // Toggle mux expansion
  const toggleMuxExpansion = (muxId: string) => {
    setExpandedMuxes((prev) => ({
      ...prev,
      [muxId]: !prev[muxId],
    }));
  };

  // Get tasks based on view mode
  const filteredTasks =
    tasks?.data?.tasks?.filter((task: TaskResponse) => {
      if (viewMode === "2q") {
        return task.task_type === "coupling";
      }
      return task.task_type === "qubit";
    }) || [];

  return (
    <div className="w-full px-6 py-6">
      <div className="space-y-6">
        {/* Header Section */}
        <div className="flex flex-col gap-6">
          <div className="flex justify-between items-center">
            <h1 className="text-2xl font-bold">Chip Experiments</h1>
            <div className="join rounded-lg overflow-hidden">
              <button
                className={`join-item btn btn-sm ${
                  viewMode === "1q" ? "btn-active" : ""
                }`}
                onClick={() => setViewMode("1q")}
              >
                <BsGrid className="text-lg" />
                <span className="ml-2">1Q View</span>
              </button>
              <button
                className={`join-item btn btn-sm ${
                  viewMode === "2q" ? "btn-active" : ""
                }`}
                onClick={() => setViewMode("2q")}
              >
                <BsGrid className="text-lg" />
                <span className="ml-2">2Q View</span>
              </button>
              <button
                className={`join-item btn btn-sm ${
                  viewMode === "mux" ? "btn-active" : ""
                }`}
                onClick={() => setViewMode("mux")}
              >
                <BsListUl className="text-lg" />
                <span className="ml-2">MUX View</span>
              </button>
            </div>
          </div>

          {/* Selection Controls */}
          <div className="flex gap-4">
            <div className="flex flex-col gap-1">
              <div className="flex justify-center gap-1 opacity-0">
                <button className="btn btn-xs btn-ghost invisible">←</button>
                <button className="btn btn-xs btn-ghost invisible">→</button>
              </div>
              <ChipSelector
                selectedChip={selectedChip}
                onChipSelect={setSelectedChip}
              />
            </div>

            <div className="flex flex-col gap-1">
              <div className="flex justify-center gap-1">
                <button
                  onClick={navigateToPreviousDay}
                  disabled={!canNavigatePrevious}
                  className="btn btn-xs btn-ghost"
                  title="Previous Day"
                >
                  ←
                </button>
                <button
                  onClick={navigateToNextDay}
                  disabled={!canNavigateNext}
                  className="btn btn-xs btn-ghost"
                  title="Next Day"
                >
                  →
                </button>
              </div>
              <DateSelector
                chipId={selectedChip}
                selectedDate={selectedDate}
                onDateSelect={setSelectedDate}
                disabled={!selectedChip}
              />
            </div>

            <div className="flex flex-col gap-1">
              <div className="flex justify-center gap-1 opacity-0">
                <button className="btn btn-xs btn-ghost invisible">←</button>
                <button className="btn btn-xs btn-ghost invisible">→</button>
              </div>
              <TaskSelector
                tasks={filteredTasks}
                selectedTask={selectedTask}
                onTaskSelect={setSelectedTask}
                disabled={viewMode === "mux"}
              />
            </div>
          </div>
        </div>

        {/* Content Section */}
        <div className="pt-4">
          {isLoadingMux ? (
            <div className="w-full flex justify-center py-12">
              <span className="loading loading-spinner loading-lg"></span>
            </div>
          ) : isMuxError ? (
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
              <span>Failed to load MUX data</span>
            </div>
          ) : !muxData?.data ? (
            <div className="alert alert-info">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                className="stroke-current shrink-0 w-6 h-6"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              <span>Select a chip to view data</span>
            </div>
          ) : viewMode === "1q" ? (
            <TaskResultGrid
              chipId={selectedChip}
              selectedTask={selectedTask}
              selectedDate={selectedDate}
              gridSize={gridSize}
              onDateChange={setSelectedDate}
            />
          ) : viewMode === "2q" ? (
            <CouplingGrid
              chipId={selectedChip}
              selectedTask={selectedTask}
              selectedDate={selectedDate}
              gridSize={gridSize}
              onDateChange={setSelectedDate}
            />
          ) : (
            <div className="space-y-4">
              {Object.entries(muxData.data.muxes).map(([muxId, muxDetail]) => {
                const updateInfo = getLatestUpdateInfo(muxDetail.detail);
                const lastUpdateText =
                  updateInfo.time.getTime() === 0
                    ? "No updates"
                    : formatRelativeTime(updateInfo.time);
                const isExpanded = expandedMuxes[muxId];
                const qids = getQidsForMux(muxDetail.mux_id);
                const taskGroups = getTaskGroups(muxDetail.detail);

                return (
                  <div
                    key={muxId}
                    className={`bg-base-100 shadow-lg rounded-xl overflow-hidden transition-all duration-200 ${
                      updateInfo.isRecent
                        ? "border-2 border-primary animate-pulse-light"
                        : "bg-base-200"
                    }`}
                  >
                    <div
                      className="p-4 cursor-pointer flex justify-between items-center hover:bg-base-200/50 transition-colors"
                      onClick={() => toggleMuxExpansion(muxId)}
                    >
                      <div className="text-xl font-medium flex items-center gap-2">
                        MUX {muxDetail.mux_id}
                        {updateInfo.isRecent && (
                          <div className="badge badge-primary gap-2 rounded-lg">
                            <div className="w-2 h-2 bg-primary-content rounded-full animate-ping" />
                            New
                          </div>
                        )}
                        <div className="badge badge-ghost gap-2 rounded-lg">
                          {Object.keys(taskGroups).length} Tasks
                        </div>
                      </div>
                      <div
                        className={`text-sm ${
                          updateInfo.isRecent
                            ? "text-primary font-medium"
                            : "text-base-content/60"
                        }`}
                      >
                        Last updated: {lastUpdateText}
                      </div>
                    </div>
                    {isExpanded && (
                      <div className="p-4 border-t">
                        {/* Task Results Grid */}
                        <div className="space-y-6">
                          {Object.entries(taskGroups).map(
                            ([taskName, qidResults]) => (
                              <div
                                key={taskName}
                                className="border-t pt-4 first:border-t-0 first:pt-0"
                              >
                                <h3 className="text-lg font-medium mb-3">
                                  {taskName}
                                </h3>
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                  {qids.map((qid) => {
                                    const task = qidResults[qid];

                                    // Show placeholder if task doesn't exist
                                    if (!task) {
                                      return (
                                        <div
                                          key={qid}
                                          className="card bg-base-200/30 shadow-sm rounded-xl overflow-hidden border border-dashed border-base-content/20"
                                        >
                                          <div className="card-body p-2">
                                            <div className="text-sm font-medium mb-2">
                                              <div className="flex justify-between items-center mb-1">
                                                <span className="text-base-content/40">QID: {qid}</span>
                                              </div>
                                            </div>
                                            <div className="text-xs text-base-content/30 italic text-center py-4">
                                              No result
                                            </div>
                                          </div>
                                        </div>
                                      );
                                    }

                                    const figurePath = getFigurePath(task);

                                    return (
                                      <div key={qid} className="relative group">
                                        <button
                                          onClick={() => {
                                            if (figurePath) {
                                              setSelectedTaskInfo({
                                                qid,
                                                task,
                                                subIndex: 0,
                                              });
                                              setModalViewMode("static");
                                            }
                                          }}
                                          className="card bg-base-100 shadow-sm rounded-xl overflow-hidden hover:shadow-md transition-shadow relative w-full"
                                        >
                                          <div className="card-body p-2">
                                            <div className="text-sm font-medium mb-2">
                                              <div className="flex justify-between items-center mb-1">
                                                <span>QID: {qid}</span>
                                                <div
                                                  className={`w-2 h-2 rounded-full ${
                                                    task.status === "completed"
                                                      ? "bg-success"
                                                      : task.status === "failed"
                                                        ? "bg-error"
                                                        : "bg-warning"
                                                  }`}
                                                />
                                              </div>
                                              {task.end_at && (
                                                <div className="text-xs text-base-content/60">
                                                  Updated:{" "}
                                                  {formatRelativeTime(
                                                    new Date(task.end_at),
                                                  )}
                                                </div>
                                              )}
                                            </div>
                                            {task.figure_path && (
                                              <div className="relative h-48 rounded-lg overflow-hidden">
                                                <TaskFigure
                                                  path={task.figure_path}
                                                  qid={qid}
                                                  className="w-full h-48 object-contain"
                                                />
                                              </div>
                                            )}
                                          </div>
                                        </button>

                                        {/* Detail Analysis Button */}
                                        <button
                                          onClick={() =>
                                            router.push(
                                              `/chip/${selectedChip}/qubit/${qid}`,
                                            )
                                          }
                                          className="absolute top-2 right-2 btn btn-xs btn-primary opacity-0 group-hover:opacity-100 transition-opacity duration-200"
                                          title="Detailed Analysis"
                                        >
                                          Detail
                                        </button>
                                      </div>
                                    );
                                  })}
                                </div>
                              </div>
                            ),
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Task Result Modal */}
      {selectedTaskInfo && (
        <dialog className="modal modal-open">
          <div className="modal-box max-w-6xl p-6 rounded-2xl shadow-xl bg-base-100">
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-bold text-lg">
                Result for QID {selectedTaskInfo.qid}
              </h3>
              <div className="flex items-center gap-2">
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
                <button
                  onClick={() =>
                    router.push(
                      `/chip/${selectedChip}/qubit/${selectedTaskInfo.qid}`,
                    )
                  }
                  className="btn btn-sm btn-primary"
                  title="Detailed Analysis"
                >
                  Detail View
                </button>
                <button
                  onClick={() => setSelectedTaskInfo(null)}
                  className="btn btn-sm btn-circle btn-ghost"
                >
                  ✕
                </button>
              </div>
            </div>

            {modalViewMode === "static" &&
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
                          onClick={() => setModalViewMode("interactive")}
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

            {modalViewMode === "interactive" &&
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
              {modalViewMode === "interactive" && (
                <button
                  className="btn btn-sm"
                  onClick={() => setModalViewMode("static")}
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
