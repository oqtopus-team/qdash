"use client";

import React, { useState } from "react";
import Link from "next/link";

import { ArrowLeft, GitBranch } from "lucide-react";

import { useGetExecution } from "@/client/execution/execution";
import { useGetCouplingMetricHistory } from "@/client/metrics/metrics";
import { TaskFigure } from "@/components/charts/TaskFigure";
import { formatDateTime, formatDateTimeCompact } from "@/utils/datetime";

interface MetricHistoryItem {
  value: number | null;
  execution_id: string;
  task_id: string | null;
  timestamp: string;
  calibrated_at: string | null;
  name: string | null;
  input_parameters: Record<string, unknown> | null;
  output_parameters: Record<string, unknown> | null;
}

/** Render a collapsible parameters table (matching ExecutionClient pattern). */
function ParametersTable({
  title,
  parameters,
}: {
  title: string;
  parameters: Record<string, unknown>;
}) {
  const entries = Object.entries(parameters);
  if (entries.length === 0) return null;

  return (
    <div className="collapse collapse-arrow border border-base-300 bg-base-100">
      <input type="checkbox" />
      <div className="collapse-title text-sm font-semibold min-h-0 py-2">
        {title}
        <span className="badge badge-xs badge-ghost ml-2">
          {entries.length}
        </span>
      </div>
      <div className="collapse-content">
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
              {entries.map(([key, val]) => {
                const paramValue =
                  typeof val === "object" && val !== null && "value" in val
                    ? (val as Record<string, unknown>)
                    : { value: val };
                return (
                  <tr key={key}>
                    <td className="font-medium">{key}</td>
                    <td className="font-mono">
                      {typeof paramValue.value === "number"
                        ? paramValue.value.toFixed(6)
                        : typeof paramValue.value === "object"
                          ? JSON.stringify(paramValue.value)
                          : String(paramValue.value ?? "N/A")}
                    </td>
                    <td>{(paramValue.unit as string) || "-"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

interface CouplingMetricHistoryModalProps {
  chipId: string;
  couplingId: string;
  metricName: string;
  metricUnit: string;
}

// Helper function to format metric value based on unit
function formatMetricValue(
  value: number | null,
  unit: string,
  precision: number = 2,
): string {
  if (value === null || value === undefined) return "N/A";
  // For percentage units, multiply by 100 to display correctly
  const displayValue = unit === "%" ? value * 100 : value;
  return displayValue.toFixed(precision);
}

export function CouplingMetricHistoryModal({
  chipId,
  couplingId,
  metricName,
  metricUnit,
}: CouplingMetricHistoryModalProps) {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [executionFilter, setExecutionFilter] = useState<string | null>(null);
  const [selectedTaskIndex, setSelectedTaskIndex] = useState(0);

  const { data, isLoading, isError } = useGetCouplingMetricHistory(
    chipId,
    couplingId,
    { metric: metricName, limit: 20, within_days: 30 },
    {
      query: {
        staleTime: 30000, // Cache for 30 seconds
        gcTime: 60000, // Keep in cache for 1 minute
      },
    },
  );

  const history = (data?.data?.history || []) as MetricHistoryItem[];

  const { data: executionDetailData, isLoading: isExecutionLoading } =
    useGetExecution(executionFilter || "", {
      query: {
        enabled: !!executionFilter,
        staleTime: 30000,
        gcTime: 60000,
      },
    });

  const executionTasks =
    executionFilter && executionDetailData?.data?.task
      ? executionDetailData.data.task.filter((t) => t.qid === couplingId)
      : [];
  const selectedTask = executionTasks[selectedTaskIndex] ?? null;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <span className="loading loading-spinner loading-lg"></span>
      </div>
    );
  }

  if (isError || history.length === 0) {
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
        <span>No history available for this metric</span>
      </div>
    );
  }

  const selectedItem = history[selectedIndex];

  // --- Execution Tasks View ---
  if (executionFilter) {
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
            {isExecutionLoading ? (
              <div className="flex items-center justify-center h-full">
                <span className="loading loading-spinner loading-lg"></span>
              </div>
            ) : selectedTask ? (
              selectedTask.figure_path ? (
                <TaskFigure
                  path={selectedTask.figure_path}
                  qid={couplingId}
                  className="w-full h-auto"
                />
              ) : selectedTask.task_id ? (
                <TaskFigure
                  taskId={selectedTask.task_id}
                  qid={couplingId}
                  className="w-full h-auto"
                />
              ) : (
                <div className="flex items-center justify-center h-full text-base-content/40">
                  No figure available
                </div>
              )
            ) : (
              <div className="flex items-center justify-center h-full text-base-content/40">
                No tasks found for {couplingId} in this execution
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
                <span className="font-mono truncate">{executionFilter}</span>
              </div>
              {selectedTask.task_id && (
                <div className="flex items-center gap-2">
                  <span className="font-semibold">Task ID:</span>
                  <span className="font-mono truncate">
                    {selectedTask.task_id}
                  </span>
                </div>
              )}
              {selectedTask.start_at && (
                <div className="flex items-center gap-2">
                  <span className="font-semibold">Start:</span>
                  <span>{formatDateTime(selectedTask.start_at as string)}</span>
                </div>
              )}
              {selectedTask.end_at && (
                <div className="flex items-center gap-2">
                  <span className="font-semibold">End:</span>
                  <span>{formatDateTime(selectedTask.end_at as string)}</span>
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
              onClick={() => {
                setExecutionFilter(null);
                setSelectedTaskIndex(0);
              }}
            >
              <ArrowLeft className="h-3 w-3" />
              Metric History
            </button>
            <h3 className="text-base sm:text-lg font-bold">Execution Tasks</h3>
            <div className="text-xs text-base-content/50 font-mono truncate">
              {executionFilter}
            </div>
          </div>
          <div className="flex-1 overflow-y-auto min-h-0">
            {isExecutionLoading ? (
              <div className="flex items-center justify-center py-8">
                <span className="loading loading-spinner loading-md"></span>
              </div>
            ) : executionTasks.length === 0 ? (
              <div className="text-sm text-base-content/50 py-4">
                No tasks found for {couplingId}
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
                          ? formatDateTimeCompact(task.start_at as string)
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
                              ? formatDateTimeCompact(task.start_at as string)
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

  // --- Metric History View (default) ---
  return (
    <div className="flex flex-col lg:flex-row gap-3 sm:gap-4 h-full">
      {/* Image Display - shown first on mobile (top), second on desktop (right) */}
      <div className="order-1 lg:order-2 lg:w-2/3 flex flex-col">
        <div className="flex items-center justify-between mb-2 sm:mb-3">
          <h3 className="text-base sm:text-lg font-bold">Calibration Result</h3>
          <div className="text-xs sm:text-sm text-base-content/60">
            {selectedIndex + 1} / {history.length}
          </div>
        </div>

        {/* Navigation Arrows */}
        <div className="flex gap-2 mb-2 sm:mb-3">
          <button
            className="btn btn-xs sm:btn-sm btn-ghost"
            disabled={selectedIndex === 0}
            onClick={() => setSelectedIndex((prev) => Math.max(0, prev - 1))}
          >
            ← Newer
          </button>
          <button
            className="btn btn-xs sm:btn-sm btn-ghost"
            disabled={selectedIndex === history.length - 1}
            onClick={() =>
              setSelectedIndex((prev) => Math.min(history.length - 1, prev + 1))
            }
          >
            Older →
          </button>
        </div>

        {/* Image Display */}
        <div className="flex-1 bg-base-200 rounded-lg p-2 sm:p-4 overflow-auto min-h-[200px] sm:min-h-[400px]">
          {selectedItem.task_id ? (
            <TaskFigure
              taskId={selectedItem.task_id}
              qid={couplingId}
              className="w-full h-auto"
            />
          ) : (
            <div className="alert alert-warning text-sm">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                className="stroke-current shrink-0 w-5 h-5 sm:w-6 sm:h-6"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                />
              </svg>
              <span>No figure available</span>
            </div>
          )}
        </div>

        {/* Metadata - hidden on mobile */}
        <div className="hidden sm:block mt-3 text-xs text-base-content/60 space-y-1 bg-base-200 p-3 rounded-lg">
          {selectedItem.name && (
            <div className="flex items-center gap-2">
              <span className="font-semibold">Task Name:</span>
              <span className="font-mono">{selectedItem.name}</span>
            </div>
          )}
          <div className="flex items-center gap-2">
            <span className="font-semibold">Execution ID:</span>
            <button
              className="font-mono truncate text-primary hover:underline cursor-pointer"
              onClick={() => {
                setExecutionFilter(selectedItem.execution_id);
                setSelectedTaskIndex(0);
              }}
              title="View all tasks for this coupling in this execution"
            >
              {selectedItem.execution_id}
            </button>
          </div>
          {selectedItem.task_id && (
            <div className="flex items-center gap-2">
              <span className="font-semibold">Task ID:</span>
              <span className="font-mono truncate">{selectedItem.task_id}</span>
            </div>
          )}
          <div className="flex items-center gap-2">
            <span className="font-semibold">Timestamp:</span>
            <span>{formatDateTime(selectedItem.timestamp)}</span>
          </div>
          {selectedItem.calibrated_at && (
            <div className="flex items-center gap-2">
              <span className="font-semibold">Calibrated At:</span>
              <span>{formatDateTime(selectedItem.calibrated_at)}</span>
            </div>
          )}
          {/* Provenance link */}
          <div className="pt-2 mt-2 border-t border-base-300">
            <Link
              href={`/provenance?parameter=${encodeURIComponent(metricName)}&qid=${encodeURIComponent(couplingId)}&tab=lineage`}
              className="btn btn-xs btn-outline gap-1"
            >
              <GitBranch className="h-3 w-3" />
              View Provenance Lineage
            </Link>
          </div>
        </div>

        {/* Input/Output Parameters - hidden on mobile */}
        <div className="hidden sm:flex flex-col gap-2 mt-2">
          {selectedItem.input_parameters &&
            Object.keys(selectedItem.input_parameters).length > 0 && (
              <ParametersTable
                title="Input Parameters"
                parameters={selectedItem.input_parameters}
              />
            )}
          {selectedItem.output_parameters &&
            Object.keys(selectedItem.output_parameters).length > 0 && (
              <ParametersTable
                title="Output Parameters"
                parameters={selectedItem.output_parameters}
              />
            )}
        </div>
      </div>

      {/* History List - shown second on mobile (bottom), first on desktop (left) */}
      <div className="order-2 lg:order-1 lg:w-1/3 flex flex-col min-h-0">
        <h3 className="text-base sm:text-lg font-bold mb-2 sm:mb-3 shrink-0">
          History
        </h3>
        <div className="flex-1 overflow-y-auto min-h-0">
          {/* Mobile: horizontal scroll list */}
          <div className="flex gap-2 overflow-x-auto pb-2 sm:hidden">
            {history.map((item, idx) => (
              <button
                key={`${item.execution_id}-${idx}`}
                onClick={() => setSelectedIndex(idx)}
                className={`flex-shrink-0 text-left p-2 rounded-lg transition-all min-w-[100px] ${
                  idx === selectedIndex
                    ? "bg-primary text-primary-content"
                    : "bg-base-200 hover:bg-base-300"
                }`}
              >
                <div className="font-bold text-sm">
                  {formatMetricValue(item.value, metricUnit, 2)} {metricUnit}
                </div>
                <div className="text-[0.65rem] opacity-70">
                  {formatDateTimeCompact(item.timestamp)}
                </div>
                {idx === 0 && (
                  <span className="badge badge-xs badge-success mt-0.5">
                    Latest
                  </span>
                )}
              </button>
            ))}
          </div>
          {/* Mobile: selected item details below cards */}
          {selectedItem && (
            <div className="sm:hidden mt-2 p-2 bg-base-200 rounded-lg text-xs space-y-1">
              <div className="flex justify-between">
                <span className="opacity-70">Execution ID:</span>
                <button
                  className="font-mono truncate max-w-[180px] text-primary hover:underline cursor-pointer"
                  onClick={() => {
                    setExecutionFilter(selectedItem.execution_id);
                    setSelectedTaskIndex(0);
                  }}
                >
                  {selectedItem.execution_id}
                </button>
              </div>
              <div className="flex justify-between">
                <span className="opacity-70">Timestamp:</span>
                <span>{formatDateTime(selectedItem.timestamp)}</span>
              </div>
            </div>
          )}
          {/* Desktop: vertical list */}
          <div className="hidden sm:flex flex-col gap-2">
            {history.map((item, idx) => (
              <button
                key={`${item.execution_id}-${idx}`}
                onClick={() => setSelectedIndex(idx)}
                className={`w-full text-left p-3 rounded-lg transition-all ${
                  idx === selectedIndex
                    ? "bg-primary text-primary-content"
                    : "bg-base-200 hover:bg-base-300"
                }`}
              >
                <div className="flex justify-between items-start">
                  <div>
                    <div className="font-bold text-lg">
                      {formatMetricValue(item.value, metricUnit, 4)}{" "}
                      {metricUnit}
                    </div>
                    <div className="text-xs opacity-70 mt-1">
                      {formatDateTimeCompact(item.timestamp)}
                    </div>
                    {idx === 0 && (
                      <span className="badge badge-sm badge-success mt-1">
                        Latest
                      </span>
                    )}
                  </div>
                  <div className="text-xs opacity-60">#{idx + 1}</div>
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
