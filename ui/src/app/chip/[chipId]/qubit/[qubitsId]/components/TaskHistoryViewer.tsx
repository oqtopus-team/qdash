"use client";

import React, { useState, useMemo } from "react";

import {
  BsCheckCircle,
  BsXCircle,
  BsClock,
  BsListUl,
  BsGrid3X3Gap,
} from "react-icons/bs";

import type { Task } from "@/schemas";

import { TaskFigure } from "@/app/components/TaskFigure";
import PlotlyRenderer from "@/app/components/PlotlyRenderer";
import { useFetchQubitTaskHistory } from "@/client/chip/chip";
import { TaskDetailModal } from "@/shared/components/TaskDetailModal";

interface TaskHistoryViewerProps {
  chipId: string;
  qubitId: string;
  taskName: string;
}

interface TaskHistoryItem extends Task {
  taskId: string;
}

export function TaskHistoryViewer({
  chipId,
  qubitId,
  taskName,
}: TaskHistoryViewerProps) {
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [historyViewMode, setHistoryViewMode] = useState<"list" | "grid">(
    "list",
  );
  const [expandedFigureIdx, setExpandedFigureIdx] = useState<number | null>(
    null,
  );
  const [modalTaskId, setModalTaskId] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<"static" | "interactive">("static");

  const { data, isLoading, error } = useFetchQubitTaskHistory(
    chipId,
    qubitId,
    taskName,
    {
      query: {
        staleTime: 30000,
      },
    },
  );

  // Convert data object to sorted array
  const taskHistory = useMemo((): TaskHistoryItem[] => {
    if (!data?.data?.data) return [];

    return Object.entries(data.data.data)
      .map(([taskId, task]) => ({
        taskId,
        ...task,
      }))
      .sort((a, b) => {
        // Sort by start_at descending (most recent first)
        const timeA = a.start_at ? new Date(a.start_at).getTime() : 0;
        const timeB = b.start_at ? new Date(b.start_at).getTime() : 0;
        return timeB - timeA;
      });
  }, [data]);

  // Auto-select first task
  React.useEffect(() => {
    if (taskHistory.length > 0 && !selectedTaskId) {
      setSelectedTaskId(taskHistory[0].taskId);
    }
  }, [taskHistory, selectedTaskId]);

  const selectedTask = useMemo(
    (): TaskHistoryItem | undefined =>
      taskHistory.find((t) => t.taskId === selectedTaskId),
    [taskHistory, selectedTaskId],
  );

  const modalTask = useMemo(
    (): TaskHistoryItem | undefined =>
      taskHistory.find((t) => t.taskId === modalTaskId),
    [taskHistory, modalTaskId],
  );

  if (isLoading) {
    return (
      <div className="flex justify-center items-center h-96">
        <span className="loading loading-spinner loading-lg"></span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="alert alert-error">
        <span>Failed to load task history: {error.message}</span>
      </div>
    );
  }

  if (taskHistory.length === 0) {
    return (
      <div className="flex justify-center items-center h-96">
        <div className="text-center text-base-content/60">
          <div className="text-4xl mb-2">📭</div>
          <div className="text-sm">No task history available</div>
        </div>
      </div>
    );
  }

  const getStatusIcon = (status?: string) => {
    switch (status) {
      case "completed":
        return <BsCheckCircle className="text-success" />;
      case "failed":
        return <BsXCircle className="text-error" />;
      default:
        return <BsClock className="text-warning" />;
    }
  };

  const getStatusBadge = (status?: string) => {
    switch (status) {
      case "completed":
        return <span className="badge badge-success badge-sm">Completed</span>;
      case "failed":
        return <span className="badge badge-error badge-sm">Failed</span>;
      default:
        return <span className="badge badge-warning badge-sm">Pending</span>;
    }
  };

  const formatDateTime = (dateStr?: string | null) => {
    if (!dateStr) return "-";
    const date = new Date(dateStr);
    return (
      <>
        <div className="font-medium">
          {date.toLocaleDateString("ja-JP", {
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
          })}
        </div>
        <div className="text-xs text-base-content/60">
          {date.toLocaleTimeString("ja-JP", {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          })}
        </div>
      </>
    );
  };

  return (
    <div className="space-y-4">
      {/* View Mode Toggle */}
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-semibold">
          Task History
          <span className="badge badge-primary ml-2">{taskHistory.length}</span>
        </h3>
        <div className="join">
          <button
            className={`join-item btn btn-sm ${
              historyViewMode === "list" ? "btn-active" : ""
            }`}
            onClick={() => setHistoryViewMode("list")}
            title="List View"
          >
            <BsListUl />
            <span className="ml-2">List</span>
          </button>
          <button
            className={`join-item btn btn-sm ${
              historyViewMode === "grid" ? "btn-active" : ""
            }`}
            onClick={() => setHistoryViewMode("grid")}
            title="Grid View"
          >
            <BsGrid3X3Gap />
            <span className="ml-2">Grid</span>
          </button>
        </div>
      </div>

      {historyViewMode === "list" ? (
        <div className="flex gap-4 h-[calc(100vh-350px)]">
          {/* Left Panel - Task History Timeline */}
          <div className="w-96 flex-shrink-0">
            <div className="card bg-base-100 shadow-xl h-full">
              <div className="card-body p-4 overflow-hidden flex flex-col">
                <h3 className="card-title text-lg mb-4">Timeline</h3>

                <div className="flex-1 overflow-y-auto space-y-2">
                  {taskHistory.map((task, index) => (
                    <div
                      key={task.taskId}
                      className={`cursor-pointer transition-all rounded-lg border-2 ${
                        selectedTaskId === task.taskId
                          ? "border-primary bg-primary/10"
                          : "border-base-300 hover:border-base-400 hover:bg-base-200"
                      }`}
                      onClick={() => setSelectedTaskId(task.taskId)}
                    >
                      <div className="p-3">
                        {/* Timeline connector */}
                        <div className="flex items-start gap-3">
                          <div className="flex flex-col items-center">
                            <div className="text-xl">
                              {getStatusIcon(task.status)}
                            </div>
                            {index < taskHistory.length - 1 && (
                              <div className="w-0.5 h-8 bg-base-300 my-1"></div>
                            )}
                          </div>

                          <div className="flex-1 min-w-0">
                            <div className="flex items-center justify-between mb-1">
                              <div className="text-xs font-mono text-base-content/60 truncate">
                                {task.taskId?.slice(-8)}
                              </div>
                              {getStatusBadge(task.status)}
                            </div>

                            <div className="text-sm">
                              {formatDateTime(task.start_at)}
                            </div>

                            {task.elapsed_time && (
                              <div className="text-xs text-base-content/60 mt-1">
                                Duration: {task.elapsed_time}
                              </div>
                            )}

                            {task.message && (
                              <div className="text-xs text-base-content/70 mt-1 truncate">
                                {task.message}
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Right Panel - Task Details */}
          <div className="flex-1 overflow-hidden">
            {selectedTask ? (
              <div className="card bg-base-100 shadow-xl h-full">
                <div className="card-body p-6 overflow-y-auto">
                  <div className="flex items-center justify-between mb-6">
                    <h3 className="card-title text-xl">Task Details</h3>
                    {getStatusBadge(selectedTask.status)}
                  </div>

                  {/* Task Information */}
                  <div className="grid grid-cols-2 gap-4 mb-6">
                    <div>
                      <div className="text-sm text-base-content/60 mb-1">
                        Task ID
                      </div>
                      <div className="font-mono text-sm break-all">
                        {selectedTask.taskId}
                      </div>
                    </div>

                    <div>
                      <div className="text-sm text-base-content/60 mb-1">
                        Task Name
                      </div>
                      <div className="font-medium">{selectedTask.name}</div>
                    </div>

                    <div>
                      <div className="text-sm text-base-content/60 mb-1">
                        Start Time
                      </div>
                      <div className="text-sm">
                        {formatDateTime(selectedTask.start_at)}
                      </div>
                    </div>

                    <div>
                      <div className="text-sm text-base-content/60 mb-1">
                        End Time
                      </div>
                      <div className="text-sm">
                        {formatDateTime(selectedTask.end_at)}
                      </div>
                    </div>

                    {selectedTask.elapsed_time && (
                      <div>
                        <div className="text-sm text-base-content/60 mb-1">
                          Duration
                        </div>
                        <div className="font-medium">
                          {selectedTask.elapsed_time}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Figures */}
                  {selectedTask.figure_path &&
                    selectedTask.figure_path.length > 0 && (
                      <div className="mb-6">
                        <h4 className="text-lg font-semibold mb-3">
                          Figures ({selectedTask.figure_path.length})
                        </h4>
                        <div className="space-y-4">
                          {selectedTask.figure_path.map((path, idx) => (
                            <div
                              key={idx}
                              className="bg-base-200 rounded-lg p-4 overflow-hidden"
                            >
                              <div className="text-sm text-base-content/60 mb-2">
                                Figure {idx + 1}
                              </div>
                              <div className="bg-white rounded-lg p-2">
                                <TaskFigure
                                  path={path}
                                  qid={qubitId}
                                  className="w-full h-auto max-h-[500px] object-contain"
                                />
                              </div>
                              {selectedTask.json_figure_path &&
                                selectedTask.json_figure_path[idx] && (
                                  <div className="mt-2 flex justify-center">
                                    <button
                                      className="btn btn-sm btn-primary"
                                      onClick={() => {
                                        setExpandedFigureIdx(idx);
                                        setViewMode("interactive");
                                      }}
                                    >
                                      Interactive View
                                    </button>
                                  </div>
                                )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                  {/* Output Parameters */}
                  {selectedTask.output_parameters && (
                    <div className="mb-6">
                      <h4 className="text-lg font-semibold mb-3">
                        Output Parameters
                      </h4>
                      <div className="overflow-x-auto">
                        <table className="table table-zebra table-sm">
                          <thead>
                            <tr>
                              <th>Parameter</th>
                              <th>Value</th>
                              <th>Unit</th>
                            </tr>
                          </thead>
                          <tbody>
                            {Object.entries(selectedTask.output_parameters).map(
                              ([key, value]) => {
                                const paramValue = (
                                  typeof value === "object" &&
                                  value !== null &&
                                  "value" in value
                                    ? value
                                    : { value }
                                ) as {
                                  value: number | string;
                                  unit?: string;
                                };
                                return (
                                  <tr key={key}>
                                    <td className="font-medium">{key}</td>
                                    <td className="font-mono">
                                      {typeof paramValue.value === "number"
                                        ? paramValue.value.toFixed(6)
                                        : String(paramValue.value)}
                                    </td>
                                    <td>{paramValue.unit || "-"}</td>
                                  </tr>
                                );
                              },
                            )}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {/* Input Parameters */}
                  {selectedTask.input_parameters && (
                    <div className="mb-6">
                      <h4 className="text-lg font-semibold mb-3">
                        Input Parameters
                      </h4>
                      <div className="overflow-x-auto">
                        <table className="table table-zebra table-sm">
                          <thead>
                            <tr>
                              <th>Parameter</th>
                              <th>Value</th>
                              <th>Unit</th>
                            </tr>
                          </thead>
                          <tbody>
                            {Object.entries(selectedTask.input_parameters).map(
                              ([key, value]) => {
                                const paramValue = (
                                  typeof value === "object" &&
                                  value !== null &&
                                  "value" in value
                                    ? value
                                    : { value }
                                ) as {
                                  value: number | string | object;
                                  unit?: string;
                                };
                                return (
                                  <tr key={key}>
                                    <td className="font-medium">{key}</td>
                                    <td className="font-mono">
                                      {typeof paramValue.value === "number"
                                        ? paramValue.value.toFixed(6)
                                        : typeof paramValue.value === "object"
                                          ? JSON.stringify(paramValue.value)
                                          : String(paramValue.value)}
                                    </td>
                                    <td>{paramValue.unit || "-"}</td>
                                  </tr>
                                );
                              },
                            )}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {/* Message */}
                  {selectedTask.message && (
                    <div>
                      <h4 className="text-lg font-semibold mb-3">Message</h4>
                      <div className="alert">
                        <span>{selectedTask.message}</span>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="card bg-base-100 shadow-xl h-full">
                <div className="card-body flex items-center justify-center">
                  <div className="text-center text-base-content/60">
                    Select a task from the history to view details
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      ) : (
        /* Grid View */
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
            {taskHistory.map((task) => {
              const figurePath =
                task.figure_path && task.figure_path.length > 0
                  ? Array.isArray(task.figure_path)
                    ? task.figure_path[0]
                    : task.figure_path
                  : null;

              return (
                <div
                  key={task.taskId}
                  className="card bg-base-100 shadow-lg hover:shadow-xl transition-all cursor-pointer group"
                  onClick={() => setModalTaskId(task.taskId)}
                >
                  <div className="card-body p-4">
                    {/* Status Badge */}
                    <div className="flex items-center justify-between mb-2">
                      <div className="text-xs font-mono text-base-content/60 truncate">
                        {task.taskId?.slice(-8)}
                      </div>
                      {getStatusBadge(task.status)}
                    </div>

                    {/* Figure */}
                    {figurePath ? (
                      <div className="bg-base-200 rounded-lg p-2 aspect-square flex items-center justify-center mb-3">
                        <TaskFigure
                          path={figurePath}
                          qid={qubitId}
                          className="w-full h-full object-contain"
                        />
                      </div>
                    ) : (
                      <div className="bg-base-200 rounded-lg p-2 aspect-square flex items-center justify-center mb-3">
                        <div className="text-center text-base-content/40">
                          <div className="text-4xl mb-2">📊</div>
                          <div className="text-xs">No Figure</div>
                        </div>
                      </div>
                    )}

                    {/* Task Info */}
                    <div className="space-y-2">
                      <div className="text-sm">
                        {formatDateTime(task.start_at)}
                      </div>

                      {task.elapsed_time && (
                        <div className="text-xs text-base-content/60">
                          ⏱ {task.elapsed_time}
                        </div>
                      )}

                      {task.message && (
                        <div className="text-xs text-base-content/70 line-clamp-2">
                          {task.message}
                        </div>
                      )}

                      {task.output_parameters && (
                        <div className="text-xs text-base-content/60">
                          {Object.keys(task.output_parameters).length}{" "}
                          parameters
                        </div>
                      )}
                    </div>

                    {/* Hover indicator */}
                    <div className="mt-2 text-center">
                      <span className="text-xs badge badge-primary opacity-0 group-hover:opacity-100 transition-opacity">
                        Click to view details
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Task Detail Modal (for Grid View) */}
      <TaskDetailModal
        isOpen={!!modalTask}
        task={modalTask || null}
        qid={qubitId}
        onClose={() => setModalTaskId(null)}
        taskId={modalTask?.taskId}
        taskName={modalTask?.name}
        variant="detailed"
      />

      {/* Figure Expansion Modal (for List View) */}
      {expandedFigureIdx !== null &&
        selectedTask &&
        selectedTask.figure_path && (
          <dialog className="modal modal-open">
            <div className="modal-box max-w-5xl w-11/12 max-h-[90vh] p-6">
              <div className="flex justify-between items-center mb-4">
                <h3 className="font-bold text-lg">
                  Figure {expandedFigureIdx + 1} of{" "}
                  {selectedTask.figure_path.length}
                </h3>
                <div className="flex items-center gap-2">
                  {expandedFigureIdx > 0 && (
                    <button
                      onClick={() =>
                        setExpandedFigureIdx(expandedFigureIdx - 1)
                      }
                      className="btn btn-sm btn-circle"
                    >
                      ←
                    </button>
                  )}
                  {expandedFigureIdx < selectedTask.figure_path.length - 1 && (
                    <button
                      onClick={() =>
                        setExpandedFigureIdx(expandedFigureIdx + 1)
                      }
                      className="btn btn-sm btn-circle"
                    >
                      →
                    </button>
                  )}
                  <button
                    onClick={() => {
                      setExpandedFigureIdx(null);
                      setViewMode("static");
                    }}
                    className="btn btn-sm btn-circle btn-ghost"
                  >
                    ✕
                  </button>
                </div>
              </div>

              {viewMode === "static" ? (
                <>
                  <div className="bg-white rounded-lg p-4 flex items-center justify-center max-h-[75vh]">
                    <TaskFigure
                      path={selectedTask.figure_path[expandedFigureIdx]}
                      qid={qubitId}
                      className="w-full h-full object-contain max-h-[70vh]"
                    />
                  </div>
                  {selectedTask.json_figure_path &&
                    selectedTask.json_figure_path[expandedFigureIdx] && (
                      <div className="mt-4 flex justify-center">
                        <button
                          className="btn btn-sm btn-primary"
                          onClick={() => setViewMode("interactive")}
                        >
                          Interactive View
                        </button>
                      </div>
                    )}
                </>
              ) : (
                <>
                  <div className="w-full h-[70vh] bg-base-200 rounded-xl p-4 shadow flex justify-center items-center">
                    <div className="w-full h-full flex justify-center items-center">
                      <div className="w-fit h-fit m-auto">
                        <PlotlyRenderer
                          className="w-full h-full"
                          fullPath={`${
                            process.env.NEXT_PUBLIC_API_URL
                          }/api/executions/figure?path=${encodeURIComponent(
                            selectedTask.json_figure_path?.[
                              expandedFigureIdx
                            ] || "",
                          )}`}
                        />
                      </div>
                    </div>
                  </div>
                  <div className="mt-4 flex justify-center">
                    <button
                      className="btn btn-sm"
                      onClick={() => setViewMode("static")}
                    >
                      Back to Static View
                    </button>
                  </div>
                </>
              )}
            </div>
            <form method="dialog" className="modal-backdrop">
              <button
                onClick={() => {
                  setExpandedFigureIdx(null);
                  setViewMode("static");
                }}
              >
                close
              </button>
            </form>
          </dialog>
        )}
    </div>
  );
}
