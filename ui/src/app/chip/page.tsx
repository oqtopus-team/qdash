"use client";

import { useState } from "react";
import { useListMuxes, useFetchChipDates } from "@/client/chip/chip";
import { useFetchAllTasks } from "@/client/task/task";
import { BsGrid, BsListUl } from "react-icons/bs";
import { Task, MuxDetailResponseDetail, TaskResponse } from "@/schemas";
import { TaskResultGrid } from "./components/TaskResultGrid";
import { ChipSelector } from "@/app/components/ChipSelector";
import { TaskSelector } from "@/app/components/TaskSelector";
import { DateSelector } from "@/app/components/DateSelector";
import { TaskFigure } from "@/app/components/TaskFigure";
type ViewMode = "chip" | "mux";

interface SelectedTaskInfo {
  path: string;
  qid: string;
  task: Task;
}

export default function ChipPage() {
  const [selectedChip, setSelectedChip] = useState<string>("");
  const [selectedDate, setSelectedDate] = useState<string>("latest");
  const [viewMode, setViewMode] = useState<ViewMode>("chip");
  const [expandedMuxes, setExpandedMuxes] = useState<{
    [key: string]: boolean;
  }>({});
  const [selectedTaskInfo, setSelectedTaskInfo] =
    useState<SelectedTaskInfo | null>(null);
  const [selectedTask, setSelectedTask] = useState<string>("CheckRabi");

  const { data: tasks } = useFetchAllTasks();
  const {
    data: muxData,
    isLoading: isLoadingMux,
    isError: isMuxError,
  } = useListMuxes(selectedChip || "");

  const {
    data: datesData,
    isLoading: isLoadingDates,
    isError: isDatesError,
  } = useFetchChipDates(selectedChip || "");

  // Get all QIDs from mux detail
  const getQids = (detail: MuxDetailResponseDetail): string[] => {
    const qids = new Set<string>();
    Object.keys(detail).forEach((qid) => qids.add(qid));
    return Array.from(qids).sort((a, b) => Number(a) - Number(b));
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
        }
      );
    });

    return taskGroups;
  };

  // Get latest update time info from tasks
  const getLatestUpdateInfo = (
    detail: MuxDetailResponseDetail
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

  // Get qubit tasks
  const qubitTasks =
    tasks?.data?.tasks?.filter(
      (task: TaskResponse) => task.task_type === "qubit"
    ) || [];

  // Set first qubit task as default if none selected and qubit tasks available
  if (selectedTask === "" && qubitTasks.length > 0) {
    setSelectedTask(qubitTasks[0].name);
  }

  return (
    <div className="w-full px-6 py-6" style={{ width: "calc(100vw - 20rem)" }}>
      <div className="space-y-6">
        {/* Header Section */}
        <div className="flex flex-col gap-6">
          <div className="flex justify-between items-center">
            <h1 className="text-2xl font-bold">Chip Experiments</h1>
            <div className="join rounded-lg overflow-hidden">
              <button
                className={`join-item btn btn-sm ${
                  viewMode === "chip" ? "btn-active" : ""
                }`}
                onClick={() => setViewMode("chip")}
              >
                <BsGrid className="text-lg" />
                <span className="ml-2">Chip View</span>
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
            <ChipSelector
              selectedChip={selectedChip}
              onChipSelect={setSelectedChip}
            />

            <DateSelector
              chipId={selectedChip}
              selectedDate={selectedDate}
              onDateSelect={setSelectedDate}
              dates={datesData?.data?.data || []}
              disabled={!selectedChip}
            />

            <TaskSelector
              tasks={qubitTasks}
              selectedTask={selectedTask}
              onTaskSelect={setSelectedTask}
              disabled={viewMode !== "chip"}
            />
          </div>
        </div>

        {/* Content Section */}
        <div className="pt-4">
          {isLoadingMux || isLoadingDates ? (
            <div className="w-full flex justify-center py-12">
              <span className="loading loading-spinner loading-lg"></span>
            </div>
          ) : isMuxError || isDatesError ? (
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
          ) : viewMode === "chip" ? (
            <TaskResultGrid
              chipId={selectedChip}
              selectedTask={selectedTask}
              selectedDate={selectedDate}
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
                const qids = getQids(muxDetail.detail);

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
                          {Object.entries(getTaskGroups(muxDetail.detail)).map(
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
                                    if (!task) return null;

                                    const figurePath = getFigurePath(task);

                                    return (
                                      <button
                                        key={qid}
                                        onClick={() => {
                                          if (figurePath) {
                                            setSelectedTaskInfo({
                                              path: figurePath,
                                              qid,
                                              task,
                                            });
                                          }
                                        }}
                                        className="card bg-base-100 shadow-sm rounded-xl overflow-hidden hover:shadow-md transition-shadow relative"
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
                                                  new Date(task.end_at)
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
                                    );
                                  })}
                                </div>
                              </div>
                            )
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
                <TaskFigure
                  path={selectedTaskInfo.path}
                  qid={selectedTaskInfo.qid}
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
