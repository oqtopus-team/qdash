"use client";

import React, { useState, useEffect } from "react";

import { ArrowLeft } from "lucide-react";

import { useGetExecution } from "@/client/execution/execution";
import { TaskFigure } from "@/components/charts/TaskFigure";
import { formatDateTime, formatDateTimeCompact } from "@/utils/datetime";

import { ParametersTable } from "./ParametersTable";

interface ExecutionTasksViewProps {
  executionId: string;
  targetId: string;
  onBack: () => void;
}

export function ExecutionTasksView({
  executionId,
  targetId,
  onBack,
}: ExecutionTasksViewProps) {
  const [selectedTaskIndex, setSelectedTaskIndex] = useState(0);

  const {
    data: executionDetailData,
    isLoading,
    isError,
  } = useGetExecution(executionId, {
    query: {
      staleTime: 30000,
      gcTime: 60000,
    },
  });

  const executionTasks = executionDetailData?.data?.task
    ? executionDetailData.data.task.filter((t) => t.qid === targetId)
    : [];

  const selectedTask = executionTasks[selectedTaskIndex] ?? null;

  // Reset index when tasks array shrinks below current selection
  useEffect(() => {
    if (
      selectedTaskIndex >= executionTasks.length &&
      executionTasks.length > 0
    ) {
      setSelectedTaskIndex(0);
    }
  }, [executionTasks.length, selectedTaskIndex]);

  return (
    <div className="flex flex-col lg:flex-row gap-3 sm:gap-4 h-full">
      {/* Task Result Display */}
      <div className="order-1 lg:order-2 lg:w-2/3 flex flex-col">
        <div className="flex items-center justify-between mb-2 sm:mb-3">
          <h3 className="text-base sm:text-lg font-bold">Task Result</h3>
          {executionTasks.length > 0 && (
            <div className="text-xs sm:text-sm text-base-content/60">
              {selectedTaskIndex + 1} / {executionTasks.length}
            </div>
          )}
        </div>

        {/* Navigation Arrows */}
        {executionTasks.length > 1 && (
          <div className="flex gap-2 mb-2 sm:mb-3">
            <button
              className="btn btn-xs sm:btn-sm btn-ghost"
              disabled={selectedTaskIndex === 0}
              onClick={() =>
                setSelectedTaskIndex((prev) => Math.max(0, prev - 1))
              }
            >
              ← Prev
            </button>
            <button
              className="btn btn-xs sm:btn-sm btn-ghost"
              disabled={selectedTaskIndex === executionTasks.length - 1}
              onClick={() =>
                setSelectedTaskIndex((prev) =>
                  Math.min(executionTasks.length - 1, prev + 1),
                )
              }
            >
              Next →
            </button>
          </div>
        )}

        {/* Figure Display */}
        <div className="flex-1 bg-base-200 rounded-lg p-2 sm:p-4 overflow-auto min-h-[200px] sm:min-h-[400px]">
          {isLoading ? (
            <div className="flex items-center justify-center h-full">
              <span className="loading loading-spinner loading-lg"></span>
            </div>
          ) : isError ? (
            <div className="flex items-center justify-center h-full text-error">
              Failed to load execution details
            </div>
          ) : selectedTask ? (
            selectedTask.figure_path ? (
              <TaskFigure
                path={selectedTask.figure_path}
                qid={targetId}
                className="w-full h-auto"
              />
            ) : selectedTask.task_id ? (
              <TaskFigure
                taskId={selectedTask.task_id}
                qid={targetId}
                className="w-full h-auto"
              />
            ) : (
              <div className="flex items-center justify-center h-full text-base-content/40">
                No figure available
              </div>
            )
          ) : (
            <div className="flex items-center justify-center h-full text-base-content/40">
              No tasks found for {targetId} in this execution
            </div>
          )}
        </div>

        {/* Task Metadata - hidden on mobile */}
        {selectedTask && (
          <div className="hidden sm:block mt-3 text-xs text-base-content/60 space-y-1 bg-base-200 p-3 rounded-lg">
            {selectedTask.name && (
              <div className="flex items-center gap-2">
                <span className="font-semibold">Task Name:</span>
                <span className="font-mono">{selectedTask.name}</span>
              </div>
            )}
            <div className="flex items-center gap-2">
              <span className="font-semibold">Execution ID:</span>
              <span className="font-mono truncate">{executionId}</span>
            </div>
            {selectedTask.task_id && (
              <div className="flex items-center gap-2">
                <span className="font-semibold">Task ID:</span>
                <span className="font-mono truncate">
                  {selectedTask.task_id}
                </span>
              </div>
            )}
            {selectedTask.start_at != null && (
              <div className="flex items-center gap-2">
                <span className="font-semibold">Start:</span>
                <span>{formatDateTime(String(selectedTask.start_at))}</span>
              </div>
            )}
            {selectedTask.end_at != null && (
              <div className="flex items-center gap-2">
                <span className="font-semibold">End:</span>
                <span>{formatDateTime(String(selectedTask.end_at))}</span>
              </div>
            )}
          </div>
        )}

        {/* Input/Output Parameters - hidden on mobile */}
        {selectedTask && (
          <div className="hidden sm:flex flex-col gap-2 mt-2">
            {selectedTask.input_parameters &&
              Object.keys(selectedTask.input_parameters).length > 0 && (
                <ParametersTable
                  title="Input Parameters"
                  parameters={
                    selectedTask.input_parameters as Record<string, unknown>
                  }
                />
              )}
            {selectedTask.output_parameters &&
              Object.keys(selectedTask.output_parameters).length > 0 && (
                <ParametersTable
                  title="Output Parameters"
                  parameters={
                    selectedTask.output_parameters as Record<string, unknown>
                  }
                />
              )}
          </div>
        )}
      </div>

      {/* Execution Tasks List */}
      <div className="order-2 lg:order-1 lg:w-1/3 flex flex-col min-h-0">
        <div className="mb-2 sm:mb-3 shrink-0">
          <button
            className="btn btn-xs sm:btn-sm btn-ghost gap-1 mb-1"
            onClick={onBack}
          >
            <ArrowLeft className="h-3 w-3" />
            Metric History
          </button>
          <h3 className="text-base sm:text-lg font-bold">Execution Tasks</h3>
          <div className="text-xs text-base-content/50 font-mono truncate">
            {executionId}
          </div>
        </div>
        <div className="flex-1 overflow-y-auto min-h-0">
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <span className="loading loading-spinner loading-md"></span>
            </div>
          ) : isError ? (
            <div className="text-sm text-error py-4">
              Failed to load execution
            </div>
          ) : executionTasks.length === 0 ? (
            <div className="text-sm text-base-content/50 py-4">
              No tasks found for {targetId}
            </div>
          ) : (
            <>
              {/* Mobile: horizontal scroll */}
              <div className="flex gap-2 overflow-x-auto pb-2 sm:hidden">
                {executionTasks.map((task, idx) => (
                  <button
                    key={task.task_id || idx}
                    onClick={() => setSelectedTaskIndex(idx)}
                    className={`flex-shrink-0 text-left p-2 rounded-lg transition-all min-w-[120px] ${
                      idx === selectedTaskIndex
                        ? "bg-primary text-primary-content"
                        : "bg-base-200 hover:bg-base-300"
                    }`}
                  >
                    <div className="font-bold text-sm truncate">
                      {task.name || "Unnamed"}
                    </div>
                    <div className="text-[0.65rem] opacity-70">
                      {task.start_at
                        ? formatDateTimeCompact(String(task.start_at))
                        : ""}
                    </div>
                    <span
                      className={`badge badge-xs mt-0.5 ${
                        task.status === "completed"
                          ? "badge-success"
                          : task.status === "failed"
                            ? "badge-error"
                            : "badge-warning"
                      }`}
                    >
                      {task.status}
                    </span>
                  </button>
                ))}
              </div>
              {/* Desktop: vertical list */}
              <div className="hidden sm:flex flex-col gap-2">
                {executionTasks.map((task, idx) => (
                  <button
                    key={task.task_id || idx}
                    onClick={() => setSelectedTaskIndex(idx)}
                    className={`w-full text-left p-3 rounded-lg transition-all ${
                      idx === selectedTaskIndex
                        ? "bg-primary text-primary-content"
                        : "bg-base-200 hover:bg-base-300"
                    }`}
                  >
                    <div className="flex justify-between items-start">
                      <div className="min-w-0 flex-1">
                        <div className="font-bold text-sm truncate">
                          {task.name || "Unnamed"}
                        </div>
                        <div className="text-xs opacity-70 mt-1">
                          {task.start_at
                            ? formatDateTimeCompact(String(task.start_at))
                            : ""}
                        </div>
                        <span
                          className={`badge badge-xs mt-1 ${
                            task.status === "completed"
                              ? "badge-success"
                              : task.status === "failed"
                                ? "badge-error"
                                : "badge-warning"
                          }`}
                        >
                          {task.status}
                        </span>
                      </div>
                      <div className="text-xs opacity-60">#{idx + 1}</div>
                    </div>
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
