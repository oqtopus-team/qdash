"use client";

import { useRouter } from "next/navigation";
import React, { useState, useEffect } from "react";

import { keepPreviousData } from "@tanstack/react-query";

import { formatDateTime } from "@/utils/datetime";

import { CouplingGrid } from "./CouplingGrid";
import { TaskResultGrid } from "./TaskResultGrid";
import { CreateChipModal } from "./modals/CreateChipModal";

import type { Task, MuxDetailResponseDetail, TaskInfo } from "@/schemas";

import { useListChipMuxes, useGetChip, useListChips } from "@/client/chip/chip";
import {
  useListTaskInfo,
  useGetTaskFileSettings,
} from "@/client/task-file/task-file";
import { TaskFigure } from "@/components/charts/TaskFigure";
import { TaskDetailModal } from "@/components/features/chip/modals/TaskDetailModal";
import { ChipSelector } from "@/components/selectors/ChipSelector";
import { DateSelector } from "@/components/selectors/DateSelector";
import { TaskSelector } from "@/components/selectors/TaskSelector";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageFiltersBar } from "@/components/ui/PageFiltersBar";
import { PageHeader } from "@/components/ui/PageHeader";
import { QuantumLoader } from "@/components/ui/QuantumLoader";
import { ChipPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";
import { useProject } from "@/contexts/ProjectContext";
import { useDateNavigation } from "@/hooks/useDateNavigation";
import { useTopologyConfig } from "@/hooks/useTopologyConfig";
import { useChipUrlState } from "@/hooks/useUrlState";

interface SelectedTaskInfo {
  qid: string;
  task: Task;
}

export function ChipPageContent() {
  const router = useRouter();
  const { canEdit } = useProject();
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

  // Use lightweight endpoints (~0.3KB vs ~300KB with embedded data)
  const { data: chipData } = useGetChip(selectedChip);
  const { data: chipsData, isLoading: isChipsLoading } = useListChips();

  // Get topology config to check if MUX is enabled
  const topologyId =
    chipData?.data?.topology_id ??
    `square-lattice-mux-${chipData?.data?.size ?? 64}`;
  const { hasMux = true } = useTopologyConfig(topologyId) ?? {};

  // Set default chip only when URL is initialized and no chip is selected from URL
  useEffect(() => {
    if (
      isInitialized &&
      !selectedChip &&
      chipsData?.data?.chips &&
      chipsData.data.chips.length > 0
    ) {
      // Sort chips by installation date and select the most recent one
      const sortedChips = [...chipsData.data.chips].sort((a, b) => {
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

  // Reset viewMode to "grid" if MUX is disabled but viewMode is "mux"
  useEffect(() => {
    if (!hasMux && viewMode === "mux") {
      setViewMode("grid");
    }
  }, [hasMux, viewMode, setViewMode]);

  const [expandedMuxes, setExpandedMuxes] = useState<{
    [key: string]: boolean;
  }>({});
  const [selectedTaskInfo, setSelectedTaskInfo] =
    useState<SelectedTaskInfo | null>(null);
  const [isCreateChipModalOpen, setIsCreateChipModalOpen] = useState(false);

  // Track previous date to distinguish modal navigation from external navigation
  const [previousDate, setPreviousDate] = useState(selectedDate);

  // Get task file settings to determine default backend
  const { data: taskFileSettings } = useGetTaskFileSettings();
  const defaultBackend = taskFileSettings?.data?.default_backend || "qubex";

  // Get task list from task-files API
  const { data: taskInfoData } = useListTaskInfo({ backend: defaultBackend });

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

    const taskList = taskInfoData?.data?.tasks || [];

    // Only set defaults if no task is selected or if the current task doesn't match the view mode
    if (viewMode === "2q" && taskList.length > 0) {
      const availableTasks = taskList.filter(
        (task: TaskInfo) => task.task_type === "coupling",
      );
      // Check if current task is valid for 2q view
      const currentTaskValid = availableTasks.some(
        (task: TaskInfo) => task.name === selectedTask,
      );

      if (!currentTaskValid) {
        const checkBellState = availableTasks.find(
          (task: TaskInfo) => task.name === "CheckBellState",
        );
        if (checkBellState) {
          setSelectedTask("CheckBellState");
        } else if (availableTasks.length > 0) {
          setSelectedTask(availableTasks[0].name);
        }
      }
    } else if (viewMode === "1q" && taskList.length > 0) {
      const availableTasks = taskList.filter(
        (task: TaskInfo) => task.task_type === "qubit",
      );
      // Check if current task is valid for 1q view
      const currentTaskValid = availableTasks.some(
        (task: TaskInfo) => task.name === selectedTask,
      );

      if (!currentTaskValid && !selectedTask) {
        // Only set default if no task is selected
        setSelectedTask("CheckRabi");
      }
    }
  }, [
    viewMode,
    taskInfoData?.data?.tasks,
    isInitialized,
    selectedTask,
    setSelectedTask,
  ]);
  const {
    data: muxData,
    isLoading: isLoadingMux,
    isError: isMuxError,
  } = useListChipMuxes(selectedChip || "", {
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
    // eslint-disable-next-line react-hooks/exhaustive-deps -- Only re-run when qid changes, not the entire selectedTaskInfo object
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
    return formatDateTime(date.toISOString());
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
  const filteredTasks = (taskInfoData?.data?.tasks || []).filter(
    (task: TaskInfo) => {
      if (viewMode === "2q") {
        return task.task_type === "coupling";
      }
      return task.task_type === "qubit";
    },
  );

  // Show skeleton during initial loading
  if (!isInitialized || isChipsLoading) {
    return <ChipPageSkeleton />;
  }

  return (
    <PageContainer>
      <div className="h-full flex flex-col space-y-3 md:space-y-4">
        {/* Header Section */}
        <div className="flex flex-col gap-3 md:gap-4">
          <PageHeader
            title="Chip Experiments"
            description="View calibration tasks and qubit results"
            actions={
              canEdit && (
                <button
                  className="btn btn-primary btn-sm w-fit"
                  onClick={() => setIsCreateChipModalOpen(true)}
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    className="h-5 w-5"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M12 4v16m8-8H4"
                    />
                  </svg>
                  Create Chip
                </button>
              )
            }
            className="mb-0"
          />

          {/* View Mode Tabs */}
          <div className="tabs tabs-boxed bg-base-200 w-fit">
            <button
              className={`tab ${viewMode === "1q" ? "tab-active" : ""}`}
              onClick={() => setViewMode("1q")}
            >
              Qubit
            </button>
            <button
              className={`tab ${viewMode === "2q" ? "tab-active" : ""}`}
              onClick={() => setViewMode("2q")}
            >
              Coupling
            </button>
            {hasMux && (
              <button
                className={`tab ${viewMode === "mux" ? "tab-active" : ""}`}
                onClick={() => setViewMode("mux")}
              >
                MUX View
              </button>
            )}
          </div>

          {/* Selection Controls */}
          <PageFiltersBar>
            <PageFiltersBar.Group>
              <PageFiltersBar.Item>
                <ChipSelector
                  selectedChip={selectedChip}
                  onChipSelect={setSelectedChip}
                />
              </PageFiltersBar.Item>
              <PageFiltersBar.Item>
                <DateSelector
                  chipId={selectedChip}
                  selectedDate={selectedDate}
                  onDateSelect={setSelectedDate}
                  disabled={!selectedChip}
                />
              </PageFiltersBar.Item>
              <PageFiltersBar.Item>
                <TaskSelector
                  tasks={filteredTasks}
                  selectedTask={selectedTask}
                  onTaskSelect={setSelectedTask}
                  disabled={viewMode === "mux"}
                />
              </PageFiltersBar.Item>
            </PageFiltersBar.Group>
          </PageFiltersBar>
        </div>

        {/* Content Section */}
        <div className="flex-1 min-h-0">
          {isLoadingMux ? (
            <div className="w-full flex justify-center py-12">
              <QuantumLoader size="lg" />
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
              topologyId={
                chipData?.data?.topology_id ??
                `square-lattice-mux-${chipData?.data?.size ?? 64}`
              }
              selectedTask={selectedTask}
              selectedDate={selectedDate}
              gridSize={gridSize}
              onDateChange={setSelectedDate}
            />
          ) : viewMode === "2q" ? (
            <CouplingGrid
              chipId={selectedChip}
              topologyId={
                chipData?.data?.topology_id ??
                `square-lattice-mux-${chipData?.data?.size ?? 64}`
              }
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
                                <div className="grid grid-cols-1 min-[400px]:grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
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
                                                <span className="text-base-content/40">
                                                  QID: {qid}
                                                </span>
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
                                              });
                                            }
                                          }}
                                          className="card bg-base-100 shadow-sm rounded-xl overflow-hidden transition-all duration-200 hover:shadow-xl hover:scale-105 relative w-full"
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
      <TaskDetailModal
        isOpen={!!selectedTaskInfo}
        task={selectedTaskInfo?.task || null}
        qid={selectedTaskInfo?.qid || ""}
        onClose={() => setSelectedTaskInfo(null)}
        chipId={selectedChip}
        selectedDate={selectedDate}
        onNavigatePrevious={navigateToPreviousDay}
        onNavigateNext={navigateToNextDay}
        canNavigatePrevious={canNavigatePrevious}
        canNavigateNext={canNavigateNext}
        formatDate={formatDate}
        taskName={selectedTaskInfo?.task?.name}
        variant="detailed"
      />

      {/* Create Chip Modal */}
      <CreateChipModal
        isOpen={isCreateChipModalOpen}
        onClose={() => setIsCreateChipModalOpen(false)}
        onSuccess={(chipId) => {
          // Automatically select the newly created chip
          setSelectedChip(chipId);
        }}
      />
    </PageContainer>
  );
}
