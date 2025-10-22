"use client";

import { useState, useMemo, useEffect } from "react";

import {
  FaExternalLinkAlt,
  FaDownload,
  FaCalendarAlt,
  FaClock,
} from "react-icons/fa";
import {
  BsCheckCircle,
  BsXCircle,
  BsClock,
} from "react-icons/bs";

import ExecutionDAG from "./ExecutionDAG";

import type { ExecutionResponseDetail } from "@/schemas";

import { LoadingSpinner } from "@/app/components/LoadingSpinner";
import { TaskFigure } from "@/app/components/TaskFigure";
import PlotlyRenderer from "@/app/components/PlotlyRenderer";
import { useFetchExecutionByChipId } from "@/client/chip/chip";

interface ExecutionDetailClientProps {
  chip_id: string;
  execute_id: string;
}

export default function ExecutionDetailClient({
  chip_id,
  execute_id,
}: ExecutionDetailClientProps) {
  const [expandedFigure, setExpandedFigure] = useState<{
    path: string;
    jsonPath?: string;
    qid: string;
    index: number;
  } | null>(null);
  const [viewMode, setViewMode] = useState<"static" | "interactive">("static");
  const [selectedTaskIndex, setSelectedTaskIndex] = useState<number | null>(
    null,
  );
  const [filterQubitId, setFilterQubitId] = useState<string>("all");
  const [filterTaskName, setFilterTaskName] = useState<string>("all");

  const calculateDetailedDuration = (start: string, end: string) => {
    const startDate = new Date(start);
    const endDate = new Date(end);
    const diff = endDate.getTime() - startDate.getTime();

    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
    const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
    const seconds = Math.floor((diff % (1000 * 60)) / 1000);

    const parts = [];
    if (days > 0) parts.push(`${days} days`);
    if (hours > 0) parts.push(`${hours} hours`);
    if (minutes > 0) parts.push(`${minutes} minutes`);
    if (seconds > 0) parts.push(`${seconds} seconds`);

    return parts.join(", ");
  };

  const {
    data: executionDetailData,
    isLoading: isDetailLoading,
    isError: isDetailError,
  } = useFetchExecutionByChipId(chip_id, execute_id, {
    query: {
      // Refresh every 5 seconds
      refetchInterval: 5000,
      // Keep polling even when the window is in the background
      refetchIntervalInBackground: true,
    },
  });

  const execution = executionDetailData?.data as
    | ExecutionResponseDetail
    | undefined;

  // Extract unique qubit IDs and task names for filtering
  const uniqueQubitIds = useMemo(() => {
    if (!execution?.task) return [];
    const qids = new Set<string>();
    execution.task.forEach((task: any) => {
      if (task.qid) {
        qids.add(task.qid);
      }
    });
    return Array.from(qids).sort();
  }, [execution?.task]);

  const uniqueTaskNames = useMemo(() => {
    if (!execution?.task) return [];
    const names = new Set<string>();
    execution.task.forEach((task: any) => {
      if (task.name) {
        names.add(task.name);
      }
    });
    return Array.from(names).sort();
  }, [execution?.task]);

  // Filter tasks based on selected filters
  const filteredTasks = useMemo(() => {
    if (!execution?.task) return [];
    return execution.task.filter((task: any) => {
      const matchesQubitId =
        filterQubitId === "all" || task.qid === filterQubitId;
      const matchesTaskName =
        filterTaskName === "all" || task.name === filterTaskName;
      return matchesQubitId && matchesTaskName;
    });
  }, [execution?.task, filterQubitId, filterTaskName]);

  // Auto-select first task when filters change
  useEffect(() => {
    if (!execution?.task) return;

    const filtered = execution.task.filter((task: any) => {
      const matchesQubitId =
        filterQubitId === "all" || task.qid === filterQubitId;
      const matchesTaskName =
        filterTaskName === "all" || task.name === filterTaskName;
      return matchesQubitId && matchesTaskName;
    });

    if (filtered.length > 0) {
      // Find the index of the first filtered task in the original task array
      const firstFilteredTaskIndex = execution.task.findIndex(
        (task: any) => task === filtered[0],
      );
      // Only update if the current selection is not in the filtered list
      const currentTaskInFilteredList =
        selectedTaskIndex !== null &&
        filtered.some((task: any) => execution.task[selectedTaskIndex] === task);

      if (!currentTaskInFilteredList) {
        setSelectedTaskIndex(firstFilteredTaskIndex);
      }
    } else {
      setSelectedTaskIndex(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterQubitId, filterTaskName, execution?.task]);

  // Filter out tasks without task_id and ensure all required fields are present
  const validTasks = useMemo(() => {
    if (!execution?.task) return [];
    return execution.task
      .filter((task) => task.task_id)
      .map((task) => {
        const taskName = task.name || "Unnamed Task";
        const displayName = task.qid ? `${task.qid}-${taskName}` : taskName;
        return {
          task_id: task.task_id as string,
          name: displayName,
          status: task.status || "unknown",
          upstream_id: task.upstream_id || undefined,
          start_at: task.start_at || undefined,
          end_at: task.end_at || undefined,
          elapsed_time: task.elapsed_time || undefined,
          figure_path: task.figure_path || undefined,
          input_parameters: task.input_parameters || undefined,
          output_parameters: task.output_parameters || undefined,
        };
      });
  }, [execution?.task]);

  const selectedTask =
    selectedTaskIndex !== null && execution?.task
      ? execution.task[selectedTaskIndex]
      : null;

  const getStatusIcon = (status?: string) => {
    switch (status) {
      case "completed":
        return <BsCheckCircle className="text-success" />;
      case "failed":
        return <BsXCircle className="text-error" />;
      case "running":
        return <BsClock className="text-info" />;
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
      case "running":
        return <span className="badge badge-info badge-sm">Running</span>;
      case "scheduled":
        return <span className="badge badge-warning badge-sm">Scheduled</span>;
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

  if (isDetailLoading) {
    return (
      <div
        className="w-full px-4 py-6 min-h-screen"
        style={{ width: "calc(100vw - 20rem)" }}
      >
        <div className="space-y-6">
          {/* Header Skeleton with Loading Spinner */}
          <div className="flex justify-between items-center">
            <div className="h-10 w-64 bg-base-300 rounded animate-pulse"></div>
            <div className="flex space-x-4">
              <div className="h-10 w-36 bg-base-300 rounded animate-pulse"></div>
              <div className="h-10 w-36 bg-base-300 rounded animate-pulse"></div>
            </div>
          </div>

          {/* Loading Spinner */}
          <div className="flex justify-center items-center py-12">
            <LoadingSpinner />
          </div>

          {/* Tasks Skeleton */}
          <div className="bg-base-100 rounded-lg shadow-md p-6">
            <div className="h-8 w-32 bg-base-300 rounded animate-pulse mb-4"></div>
            <div className="space-y-4">
              {[1, 2].map((i) => (
                <div
                  key={i}
                  className="bg-base-100 rounded-lg shadow-md border-l-4 border-base-300"
                >
                  <div className="p-4">
                    <div className="flex justify-between items-center mb-2">
                      <div className="h-6 w-48 bg-base-300 rounded animate-pulse"></div>
                      <div className="h-6 w-24 bg-base-300 rounded animate-pulse"></div>
                    </div>
                    <div className="space-y-2">
                      <div className="h-4 w-36 bg-base-300 rounded animate-pulse"></div>
                      <div className="h-4 w-32 bg-base-300 rounded animate-pulse"></div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  }
  if (isDetailError) return <div>Error loading execution details.</div>;
  if (!executionDetailData || !execution) return <div>No data found.</div>;

  return (
    <div className="w-full px-4 py-6" style={{ width: "calc(100vw - 20rem)" }}>
      <div className="space-y-6">
        <div className="space-y-4">
          <div className="flex justify-between items-center">
            <h1 className="text-3xl font-bold">{execution.name}</h1>
            <div className="flex space-x-4">
              <a
                href={`/execution/${execute_id}/experiment`}
                className="bg-neutral text-neutral-content px-4 py-2 rounded flex items-center hover:opacity-80 transition-colors"
              >
                <FaExternalLinkAlt className="mr-2" />
                Go to Experiment
              </a>
              <a
                href={(execution.note as { [key: string]: any })?.ui_url || "#"}
                className="bg-accent text-accent-content px-4 py-2 rounded flex items-center hover:opacity-80 transition-colors"
              >
                <FaExternalLinkAlt className="mr-2" />
                Go to Flow
              </a>
            </div>
          </div>

          <div className="flex items-center gap-6 text-sm bg-base-100/50 px-4 py-3 rounded-lg">
            <div className="flex items-center text-base-content/70">
              <FaCalendarAlt className="mr-2 text-info/70" />
              <span className="font-medium mr-1">Start:</span>
              <time>{new Date(execution.start_at).toLocaleString()}</time>
            </div>
            <div className="flex items-center text-base-content/70">
              <FaCalendarAlt className="mr-2 text-info/70" />
              <span className="font-medium mr-1">End:</span>
              <time>{new Date(execution.end_at).toLocaleString()}</time>
            </div>
            <div
              className="flex items-center text-base-content/70 tooltip tooltip-bottom"
              data-tip={calculateDetailedDuration(
                execution.start_at,
                execution.end_at,
              )}
            >
              <FaClock className="mr-2 text-info/70" />
              <span className="font-medium mr-1">Duration:</span>
              <span>{execution.elapsed_time}</span>
            </div>
          </div>
        </div>

        <div className="bg-base-100 rounded-lg shadow-md p-6">
          <h2 className="text-xl font-bold mb-4">Execution Flow</h2>
          <ExecutionDAG tasks={validTasks} />
        </div>

        <div className="bg-base-100 rounded-lg shadow-md p-6">
          <h2 className="text-xl font-bold mb-4">
            Tasks
            <span className="badge badge-primary ml-2">
              {filteredTasks.length}
              {filteredTasks.length !== execution.task?.length &&
                ` / ${execution.task?.length || 0}`}
            </span>
          </h2>

          <div className="flex gap-4 h-[calc(100vh-400px)]">
            {/* Left Panel - Task Timeline */}
            <div className="w-96 flex-shrink-0">
              <div className="card bg-base-100 shadow-xl h-full">
                <div className="card-body p-4 overflow-hidden flex flex-col">
                  <h3 className="card-title text-lg mb-2">Timeline</h3>

                  {/* Filter Controls */}
                  <div className="space-y-2 mb-4">
                    <div className="form-control">
                      <label className="label py-1">
                        <span className="label-text text-xs font-semibold">
                          Qubit ID
                        </span>
                      </label>
                      <select
                        className="select select-bordered select-sm w-full"
                        value={filterQubitId}
                        onChange={(e) => setFilterQubitId(e.target.value)}
                      >
                        <option value="all">All Qubits</option>
                        {uniqueQubitIds.map((qid) => (
                          <option key={qid} value={qid}>
                            {qid}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="form-control">
                      <label className="label py-1">
                        <span className="label-text text-xs font-semibold">
                          Task Name
                        </span>
                      </label>
                      <select
                        className="select select-bordered select-sm w-full"
                        value={filterTaskName}
                        onChange={(e) => setFilterTaskName(e.target.value)}
                      >
                        <option value="all">All Tasks</option>
                        {uniqueTaskNames.map((name) => (
                          <option key={name} value={name}>
                            {name}
                          </option>
                        ))}
                      </select>
                    </div>

                    {(filterQubitId !== "all" || filterTaskName !== "all") && (
                      <button
                        className="btn btn-xs btn-ghost w-full"
                        onClick={() => {
                          setFilterQubitId("all");
                          setFilterTaskName("all");
                        }}
                      >
                        Clear Filters
                      </button>
                    )}
                  </div>

                  <div className="flex-1 overflow-y-auto space-y-2">
                    {filteredTasks.length === 0 ? (
                      <div className="flex items-center justify-center h-full text-base-content/60 text-sm">
                        No tasks match the selected filters
                      </div>
                    ) : (
                      filteredTasks.map((task: any, filteredIndex: number) => {
                        // Find the original index in execution.task
                        const originalIndex = execution.task.findIndex(
                          (t: any) => t === task,
                        );
                        return (
                          <div
                            key={originalIndex}
                            className={`cursor-pointer transition-all rounded-lg border-2 ${
                              selectedTaskIndex === originalIndex
                                ? "border-primary bg-primary/10"
                                : "border-base-300 hover:border-base-400 hover:bg-base-200"
                            }`}
                            onClick={() => setSelectedTaskIndex(originalIndex)}
                          >
                            <div className="p-3">
                              {/* Timeline connector */}
                              <div className="flex items-start gap-3">
                                <div className="flex flex-col items-center">
                                  <div className="text-xl">
                                    {getStatusIcon(task.status)}
                                  </div>
                                  {filteredIndex < filteredTasks.length - 1 && (
                                    <div className="w-0.5 h-8 bg-base-300 my-1"></div>
                                  )}
                                </div>

                                <div className="flex-1 min-w-0">
                                  <div className="flex items-center justify-between mb-1">
                                    <div className="text-sm font-semibold truncate">
                                      {task.name}
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

                                  {task.qid && (
                                    <div className="text-xs text-base-content/70 mt-1 truncate">
                                      Qubit: {task.qid}
                                    </div>
                                  )}
                                </div>
                              </div>
                            </div>
                          </div>
                        );
                      })
                    )}
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
                      <h3 className="card-title text-xl">{selectedTask.name}</h3>
                      {getStatusBadge(selectedTask.status)}
                    </div>

                    {/* Task Information */}
                    <div className="grid grid-cols-2 gap-4 mb-6">
                      <div>
                        <div className="text-sm text-base-content/60 mb-1">
                          Task ID
                        </div>
                        <div className="font-mono text-sm break-all">
                          {selectedTask.task_id || "N/A"}
                        </div>
                      </div>

                      <div>
                        <div className="text-sm text-base-content/60 mb-1">
                          Qubit ID
                        </div>
                        <div className="font-medium">{selectedTask.qid || "N/A"}</div>
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

                    {/* Raw Data Files */}
                    {selectedTask.raw_data_path &&
                      selectedTask.raw_data_path.length > 0 && (
                        <div className="mb-6">
                          <h4 className="text-lg font-semibold mb-3">
                            Raw Data ({selectedTask.raw_data_path.length})
                          </h4>
                          <div className="space-y-2">
                            {selectedTask.raw_data_path.map(
                              (path: string, i: number) => (
                                <div
                                  key={i}
                                  className="flex items-center justify-between bg-base-200 p-2 rounded"
                                >
                                  <span className="text-sm truncate flex-1 mr-4">
                                    {path.split("/").pop()}
                                  </span>
                                  <button
                                    onClick={() => {
                                      const link = document.createElement("a");
                                      const normalizedPath = path.startsWith("/")
                                        ? path
                                        : `/${path}`;
                                      const apiUrl =
                                        process.env.NEXT_PUBLIC_API_URL;
                                      link.href = `${apiUrl}/api/file/raw_data?path=${encodeURIComponent(
                                        normalizedPath,
                                      )}`;
                                      const filename =
                                        path.split("/").pop() || "file";
                                      link.download = filename;
                                      document.body.appendChild(link);
                                      link.click();
                                      document.body.removeChild(link);
                                    }}
                                    className="btn btn-sm btn-primary"
                                  >
                                    <FaDownload className="mr-2" />
                                    Download
                                  </button>
                                </div>
                              ),
                            )}
                          </div>
                        </div>
                      )}

                    {/* Figures */}
                    {selectedTask.figure_path &&
                      (Array.isArray(selectedTask.figure_path)
                        ? selectedTask.figure_path.length > 0
                        : true) && (
                        <div className="mb-6">
                          <h4 className="text-lg font-semibold mb-3">
                            Figures (
                            {Array.isArray(selectedTask.figure_path)
                              ? selectedTask.figure_path.length
                              : 1}
                            )
                          </h4>
                          <div className="space-y-4">
                            {(Array.isArray(selectedTask.figure_path)
                              ? selectedTask.figure_path
                              : [selectedTask.figure_path]
                            ).map((path: string, idx: number) => (
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
                                    qid={selectedTask.qid || ""}
                                    className="w-full h-auto max-h-[500px] object-contain"
                                  />
                                </div>
                                {selectedTask.json_figure_path &&
                                  selectedTask.json_figure_path[idx] && (
                                    <div className="mt-2 flex justify-center">
                                      <button
                                        className="btn btn-sm btn-primary"
                                        onClick={() => {
                                          setExpandedFigure({
                                            path,
                                            jsonPath:
                                              selectedTask.json_figure_path?.[idx] || "",
                                            qid: selectedTask.qid || "",
                                            index: idx,
                                          });
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
                                ([key, value]: [string, any]) => {
                                  const paramValue =
                                    typeof value === "object" &&
                                    value !== null &&
                                    "value" in value
                                      ? value
                                      : { value };
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
                                ([key, value]: [string, any]) => {
                                  const paramValue =
                                    typeof value === "object" &&
                                    value !== null &&
                                    "value" in value
                                      ? value
                                      : { value };
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
                      Select a task from the timeline to view details
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Figure Expansion Modal */}
      {expandedFigure && (
        <dialog className="modal modal-open">
          <div className="modal-box max-w-5xl w-11/12 max-h-[90vh] p-6">
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-bold text-lg">
                Figure {expandedFigure.index + 1}
              </h3>
              <button
                onClick={() => {
                  setExpandedFigure(null);
                  setViewMode("static");
                }}
                className="btn btn-sm btn-circle btn-ghost"
              >
                ✕
              </button>
            </div>

            {viewMode === "static" ? (
              <>
                <div className="bg-white rounded-lg p-4 flex items-center justify-center max-h-[75vh]">
                  <TaskFigure
                    path={expandedFigure.path}
                    qid={expandedFigure.qid}
                    className="w-full h-full object-contain max-h-[70vh]"
                  />
                </div>
                {expandedFigure.jsonPath && (
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
                          expandedFigure.jsonPath || "",
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
                setExpandedFigure(null);
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
