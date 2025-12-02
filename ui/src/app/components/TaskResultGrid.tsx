"use client";

import { useState } from "react";

import { TaskFigure } from "./TaskFigure";

import type { Task } from "@/schemas";

import {
  useFetchLatestQubitTaskResults,
  useFetchHistoricalQubitTaskResults,
} from "@/client/task-result/task-result";

interface TaskResultGridProps {
  chipId: string;
  selectedTask: string;
  selectedDate: string;
}

interface SelectedTaskInfo {
  path: string;
  qid: string;
  task: Task;
}

export function TaskResultGrid({
  chipId,
  selectedTask,
  selectedDate,
}: TaskResultGridProps) {
  const [selectedTaskInfo, setSelectedTaskInfo] =
    useState<SelectedTaskInfo | null>(null);

  // Use appropriate hook based on selectedDate
  const {
    data: latestData,
    isLoading: isLoadingLatest,
    isError: isLatestError,
  } = useFetchLatestQubitTaskResults(
    { chip_id: chipId, task: selectedTask },
    {
      query: {
        enabled: selectedDate === "latest",
      },
    },
  );

  const {
    data: historicalData,
    isLoading: isLoadingHistorical,
    isError: isHistoricalError,
  } = useFetchHistoricalQubitTaskResults(
    { chip_id: chipId, task: selectedTask, date: selectedDate },
    {
      query: {
        enabled: selectedDate !== "latest",
      },
    },
  );

  const isLoading = isLoadingLatest || isLoadingHistorical;
  const isError = isLatestError || isHistoricalError;
  const responseData =
    selectedDate === "latest" ? latestData?.data : historicalData?.data;

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

  if (isLoading) {
    return (
      <div className="w-full flex justify-center py-12">
        <span className="loading loading-spinner loading-lg"></span>
      </div>
    );
  }

  if (isError) {
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
        <span>Failed to load task results</span>
      </div>
    );
  }

  if (!responseData) {
    return (
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
        <span>No task results available</span>
      </div>
    );
  }

  return (
    <>
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
        {Object.entries(responseData.result).map(
          ([qid, task]: [string, Task]) => {
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
                        Updated: {formatRelativeTime(new Date(task.end_at))}
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
          },
        )}
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
                        selectedTaskInfo.task.output_parameters,
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
    </>
  );
}
