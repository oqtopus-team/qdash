"use client";

import { useState } from "react";
import { useListChips, useListMuxes } from "@/client/chip/chip";
import { BsGrid, BsListUl } from "react-icons/bs";
import { ServerRoutersChipTask, MuxDetailResponseDetail } from "@/schemas";
import { TaskResultGrid } from "./components/TaskResultGrid";

type ViewMode = "chip" | "mux";
type TaskViewMode = "image" | "params";
type LayoutMode = "list" | "grid";

interface TaskCardState {
  [key: string]: TaskViewMode;
}

interface ParameterValue {
  value: number | string;
  unit?: string;
  calibrated_at?: string;
}

export default function ChipPage() {
  const [selectedChip, setSelectedChip] = useState<string>("SAMPLE");
  const [viewMode, setViewMode] = useState<ViewMode>("chip");
  const [viewModes, setViewModes] = useState<TaskCardState>({});
  const [layoutMode, setLayoutMode] = useState<LayoutMode>("list");
  const [expandedMuxes, setExpandedMuxes] = useState<{
    [key: string]: boolean;
  }>({});

  const { data: chips } = useListChips();
  const {
    data: muxData,
    isLoading,
    isError,
  } = useListMuxes(selectedChip || "");

  // Get all QIDs from mux detail
  const getQids = (detail: MuxDetailResponseDetail): string[] => {
    const qids = new Set<string>();
    Object.keys(detail).forEach((qid) => qids.add(qid));
    return Array.from(qids).sort((a, b) => Number(a) - Number(b));
  };

  // Group tasks by name for each mux
  const getTaskGroups = (detail: MuxDetailResponseDetail) => {
    const taskGroups: {
      [key: string]: { [key: string]: ServerRoutersChipTask };
    } = {};

    // Iterate through each QID in the mux detail
    Object.entries(detail).forEach(([qid, tasksByName]) => {
      // Iterate through each task
      Object.entries(
        tasksByName as { [key: string]: ServerRoutersChipTask }
      ).forEach(([taskName, task]) => {
        if (task.status !== "completed" && task.status !== "failed") return;

        if (!taskGroups[taskName]) {
          taskGroups[taskName] = {};
        }
        taskGroups[taskName][qid] = task;
      });
    });

    return taskGroups;
  };

  // Get latest update time info from tasks
  const getLatestUpdateInfo = (
    detail: MuxDetailResponseDetail
  ): { time: Date; isRecent: boolean } => {
    let latestTime = new Date(0);

    Object.values(detail).forEach((tasksByName) => {
      Object.values(
        tasksByName as { [key: string]: ServerRoutersChipTask }
      ).forEach((task) => {
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

  // Toggle view mode for a task
  const toggleViewMode = (taskId: string) => {
    setViewModes((prev) => ({
      ...prev,
      [taskId]: prev[taskId] === "image" ? "params" : "image",
    }));
  };

  // Get view mode for a task
  const getViewMode = (taskId: string): TaskViewMode => {
    return viewModes[taskId] || "image";
  };

  // Toggle mux expansion
  const toggleMuxExpansion = (muxId: string) => {
    setExpandedMuxes((prev) => ({
      ...prev,
      [muxId]: !prev[muxId],
    }));
  };

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

          {/* Chip Selection */}
          <select
            className="select select-bordered w-full max-w-xs rounded-lg"
            value={selectedChip}
            onChange={(e) => setSelectedChip(e.target.value)}
          >
            <option value="">Select a chip</option>
            {chips?.data.map((chip) => (
              <option key={chip.chip_id} value={chip.chip_id}>
                {chip.chip_id}
              </option>
            ))}
          </select>
        </div>

        {/* Content Section */}
        <div className="pt-4">
          {isLoading ? (
            <div className="w-full flex justify-center py-12">
              <span className="loading loading-spinner loading-lg"></span>
            </div>
          ) : isError ? (
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
            <TaskResultGrid chipId={selectedChip} />
          ) : (
            <div
              className={
                layoutMode === "grid" ? "grid grid-cols-4 gap-4" : "space-y-4"
              }
            >
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
                    } ${layoutMode === "grid" ? "min-h-[3rem]" : ""}`}
                    style={{
                      gridColumn: isExpanded ? "1 / -1" : "auto",
                    }}
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
                                    const taskId = `${muxId}-${qid}-${taskName}`;
                                    const viewMode = getViewMode(taskId);

                                    return (
                                      <div
                                        key={qid}
                                        className="card bg-base-100 shadow-sm rounded-xl overflow-hidden"
                                      >
                                        <div className="card-body p-2">
                                          <div className="text-sm font-medium mb-2">
                                            <div className="flex justify-between items-center mb-1">
                                              <span>QID: {qid}</span>
                                              {task?.output_parameters && (
                                                <div className="tabs tabs-boxed rounded-lg">
                                                  <a
                                                    className={`tab tab-xs ${
                                                      viewMode === "image"
                                                        ? "tab-active"
                                                        : ""
                                                    }`}
                                                    onClick={() =>
                                                      toggleViewMode(taskId)
                                                    }
                                                  >
                                                    Image
                                                  </a>
                                                  <a
                                                    className={`tab tab-xs ${
                                                      viewMode === "params"
                                                        ? "tab-active"
                                                        : ""
                                                    }`}
                                                    onClick={() =>
                                                      toggleViewMode(taskId)
                                                    }
                                                  >
                                                    Params
                                                  </a>
                                                </div>
                                              )}
                                            </div>
                                            {task?.end_at && (
                                              <div className="text-xs text-base-content/60">
                                                Updated:{" "}
                                                {formatRelativeTime(
                                                  new Date(task.end_at)
                                                )}
                                              </div>
                                            )}
                                          </div>
                                          {task &&
                                            viewMode === "image" &&
                                            task.figure_path && (
                                              <div className="relative h-48 rounded-lg overflow-hidden">
                                                {Array.isArray(
                                                  task.figure_path
                                                ) ? (
                                                  task.figure_path.map(
                                                    (path, i) => (
                                                      <img
                                                        key={i}
                                                        src={`http://localhost:5715/executions/figure?path=${encodeURIComponent(
                                                          path
                                                        )}`}
                                                        alt={`Result for QID ${qid}`}
                                                        className="w-full h-48 object-contain"
                                                      />
                                                    )
                                                  )
                                                ) : (
                                                  <img
                                                    src={`http://localhost:5715/executions/figure?path=${encodeURIComponent(
                                                      task.figure_path
                                                    )}`}
                                                    alt={`Result for QID ${qid}`}
                                                    className="w-full h-48 object-contain"
                                                  />
                                                )}
                                              </div>
                                            )}
                                          {task &&
                                            viewMode === "params" &&
                                            task.output_parameters && (
                                              <div className="h-48 overflow-y-auto rounded-lg">
                                                <table className="table table-xs table-zebra w-full rounded-lg overflow-hidden">
                                                  <thead>
                                                    <tr>
                                                      <th className="rounded-tl-lg">
                                                        Parameter
                                                      </th>
                                                      <th>Value</th>
                                                      <th className="rounded-tr-lg">
                                                        Updated
                                                      </th>
                                                    </tr>
                                                  </thead>
                                                  <tbody className="text-xs">
                                                    {Object.entries(
                                                      task.output_parameters
                                                    ).map(([key, value]) => {
                                                      const paramValue =
                                                        typeof value ===
                                                          "object" &&
                                                        value !== null &&
                                                        "value" in value
                                                          ? (value as ParameterValue)
                                                          : ({
                                                              value,
                                                            } as ParameterValue);
                                                      return (
                                                        <tr key={key}>
                                                          <td className="font-medium py-0.5">
                                                            {key}
                                                          </td>
                                                          <td className="text-right py-0.5">
                                                            {typeof paramValue.value ===
                                                            "number"
                                                              ? paramValue.value.toFixed(
                                                                  4
                                                                )
                                                              : String(
                                                                  paramValue.value
                                                                )}
                                                            {paramValue.unit
                                                              ? ` ${paramValue.unit}`
                                                              : ""}
                                                          </td>
                                                          <td className="text-right py-0.5 text-base-content/60">
                                                            {paramValue.calibrated_at
                                                              ? new Date(
                                                                  paramValue.calibrated_at
                                                                ).toLocaleString()
                                                              : "-"}
                                                          </td>
                                                        </tr>
                                                      );
                                                    })}
                                                  </tbody>
                                                </table>
                                              </div>
                                            )}
                                        </div>
                                      </div>
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
    </div>
  );
}
