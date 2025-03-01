"use client";

import { useListChips, useListMuxes } from "@/client/chip/chip";
import { useState } from "react";
import {
  ListMuxResponse,
  ServerRoutersChipTask,
  MuxDetailResponseDetail,
} from "@/schemas";

type ViewMode = "image" | "params";

interface TaskCardState {
  [key: string]: ViewMode;
}

interface ParameterValue {
  value: number | string;
  unit?: string;
  calibrated_at?: string;
}

export default function ChipPage() {
  const [selectedChip, setSelectedChip] = useState<string>("SAMPLE");
  const [viewModes, setViewModes] = useState<TaskCardState>({});
  const { data: chips } = useListChips();
  const { data: muxData } = useListMuxes(selectedChip || "");

  // Group tasks by name for each mux
  const getTaskGroups = (muxId: string, detail: MuxDetailResponseDetail) => {
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
    const isRecent = now.getTime() - latestTime.getTime() < 24 * 60 * 60 * 1000; // 24時間以内

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
  const getViewMode = (taskId: string): ViewMode => {
    return viewModes[taskId] || "image";
  };

  return (
    <div className="w-full px-4 py-6" style={{ width: "calc(100vw - 20rem)" }}>
      <div className="space-y-6">
        <div className="mb-8">
          <h1 className="text-2xl font-bold mb-4">Chip Experiments</h1>

          {/* Chip Selection */}
          <select
            className="select select-bordered w-full max-w-xs"
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

        {/* MUX Accordions */}
        {muxData?.data && (
          <div className="space-y-4">
            {Object.entries(muxData.data.muxes).map(([muxId, muxDetail]) => {
              const updateInfo = getLatestUpdateInfo(muxDetail.detail);
              const lastUpdateText =
                updateInfo.time.getTime() === 0
                  ? "No updates"
                  : formatRelativeTime(updateInfo.time);

              return (
                <div
                  key={muxId}
                  className={`collapse collapse-arrow bg-base-100 shadow-lg ${
                    updateInfo.isRecent
                      ? "border-2 border-primary animate-pulse-light"
                      : "bg-base-200"
                  }`}
                >
                  <input type="checkbox" />
                  <div className="collapse-title">
                    <div className="flex justify-between items-center">
                      <div className="text-xl font-medium flex items-center gap-2">
                        MUX {muxDetail.mux_id}
                        {updateInfo.isRecent && (
                          <div className="badge badge-primary gap-2">
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
                  </div>
                  <div className="collapse-content">
                    {/* Task Results Grid */}
                    <div className="space-y-6">
                      {Object.entries(
                        getTaskGroups(muxId, muxDetail.detail)
                      ).map(([taskName, qidResults]) => (
                        <div
                          key={taskName}
                          className="border-t pt-4 first:border-t-0 first:pt-0"
                        >
                          <h3 className="text-lg font-medium mb-3">
                            {taskName}
                          </h3>
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                            {Object.entries(qidResults).map(([qid, task]) => {
                              const taskId = `${muxId}-${qid}-${taskName}`;
                              const viewMode = getViewMode(taskId);

                              return (
                                <div
                                  key={qid}
                                  className="card bg-base-100 shadow-sm"
                                >
                                  <div className="card-body p-2">
                                    <div className="text-sm font-medium mb-2">
                                      <div className="flex justify-between items-center mb-1">
                                        <span>QID: {qid}</span>
                                        {task.output_parameters && (
                                          <div className="tabs tabs-boxed">
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
                                      {task.end_at && (
                                        <div className="text-xs text-base-content/60">
                                          Updated:{" "}
                                          {formatRelativeTime(
                                            new Date(task.end_at)
                                          )}
                                        </div>
                                      )}
                                    </div>
                                    {viewMode === "image" &&
                                      task.figure_path && (
                                        <div className="relative h-48">
                                          {Array.isArray(task.figure_path) ? (
                                            task.figure_path.map((path, i) => (
                                              <img
                                                key={i}
                                                src={`http://localhost:5715/executions/figure?path=${encodeURIComponent(
                                                  path
                                                )}`}
                                                alt={`Result for QID ${qid}`}
                                                className="w-full h-48 object-contain"
                                              />
                                            ))
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
                                    {viewMode === "params" &&
                                      task.output_parameters && (
                                        <div className="h-48 overflow-y-auto">
                                          <table className="table table-xs table-zebra w-full">
                                            <thead>
                                              <tr>
                                                <th>Parameter</th>
                                                <th>Value</th>
                                                <th>Updated</th>
                                              </tr>
                                            </thead>
                                            <tbody className="text-xs">
                                              {Object.entries(
                                                task.output_parameters
                                              ).map(([key, value]) => {
                                                const paramValue =
                                                  typeof value === "object" &&
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
                      ))}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
