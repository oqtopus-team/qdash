"use client";

import React, { useState, useMemo, useEffect } from "react";
import Link from "next/link";

import {
  ChevronRight,
  GitBranch,
  History,
  ListTodo,
  FileText,
  Bot,
} from "lucide-react";

import { useGetQubitMetricHistory } from "@/client/metrics/metrics";
import { useGetExecution } from "@/client/execution/execution";
import { TaskFigure } from "@/components/charts/TaskFigure";
import { formatDateTime, formatDateTimeCompact } from "@/lib/utils/datetime";

import { ParametersTable } from "./ParametersTable";
import { TaskResultIssues } from "./TaskResultIssues";
import type { AnalysisContext } from "@/hooks/useAnalysisChat";
import type { MetricHistoryItem } from "./MetricHistoryView";
import { useAnalysisChatContext } from "@/contexts/AnalysisChatContext";

interface QubitMetricHistoryModalProps {
  chipId: string;
  qid: string;
  metricName: string;
  metricUnit: string;
}

interface ExecutionGroup {
  executionId: string;
  timestamp: string;
  items: MetricHistoryItem[];
}

function formatMetricValue(
  value: number | null,
  unit: string,
  precision: number = 2,
): string {
  if (value === null || value === undefined) return "N/A";
  const displayValue = unit === "%" ? value * 100 : value;
  return displayValue.toFixed(precision);
}

// Mobile tab type
type MobileTab = "history" | "tasks" | "details";

export function QubitMetricHistoryModal({
  chipId,
  qid,
  metricName,
  metricUnit,
}: QubitMetricHistoryModalProps) {
  const [selectedExecutionId, setSelectedExecutionId] = useState<string | null>(
    null,
  );
  const [selectedTaskIndex, setSelectedTaskIndex] = useState(0);
  const [mobileTab, setMobileTab] = useState<MobileTab>("history");
  const { openAnalysisChat } = useAnalysisChatContext();

  const { data, isLoading, isError } = useGetQubitMetricHistory(
    chipId,
    qid,
    { metric: metricName, limit: 20, within_days: 30 },
    {
      query: {
        staleTime: 30000,
        gcTime: 60000,
      },
    },
  );

  const history = useMemo(
    () => (data?.data?.history || []) as MetricHistoryItem[],
    [data?.data?.history],
  );

  // Group history items by execution_id
  const executionGroups = useMemo(() => {
    const groups = new Map<string, ExecutionGroup>();
    history.forEach((item) => {
      if (!groups.has(item.execution_id)) {
        groups.set(item.execution_id, {
          executionId: item.execution_id,
          timestamp: item.timestamp,
          items: [],
        });
      }
      groups.get(item.execution_id)!.items.push(item);
    });
    // Sort by timestamp (newest first)
    return Array.from(groups.values()).sort(
      (a, b) =>
        new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
    );
  }, [history]);

  // Fetch execution details when an execution is selected
  const {
    data: executionDetailData,
    isLoading: isExecutionLoading,
    isError: isExecutionError,
  } = useGetExecution(selectedExecutionId || "", {
    query: {
      enabled: !!selectedExecutionId,
      staleTime: 30000,
      gcTime: 60000,
    },
  });

  // Tasks for the selected execution filtered by target qid
  const executionTasks = useMemo(() => {
    if (!executionDetailData?.data?.task) return [];
    return executionDetailData.data.task.filter((t) => t.qid === qid);
  }, [executionDetailData, qid]);

  const selectedGroup = executionGroups.find(
    (g) => g.executionId === selectedExecutionId,
  );

  // Auto-select first execution when data loads
  useEffect(() => {
    if (executionGroups.length > 0 && !selectedExecutionId) {
      setSelectedExecutionId(executionGroups[0].executionId);
    }
  }, [executionGroups, selectedExecutionId]);

  // Reset task index when execution changes, using task_id from history data
  useEffect(() => {
    if (executionTasks.length > 0 && selectedGroup) {
      // Find the task_id from history that corresponds to this metric
      const historyTaskId = selectedGroup.items[0]?.task_id;
      if (historyTaskId) {
        const matchingIndex = executionTasks.findIndex(
          (task) => task.task_id === historyTaskId,
        );
        setSelectedTaskIndex(matchingIndex >= 0 ? matchingIndex : 0);
      } else {
        setSelectedTaskIndex(0);
      }
    } else {
      setSelectedTaskIndex(0);
    }
  }, [selectedExecutionId, executionTasks, selectedGroup]);

  // Ensure task index is valid
  useEffect(() => {
    if (
      selectedTaskIndex >= executionTasks.length &&
      executionTasks.length > 0
    ) {
      setSelectedTaskIndex(0);
    }
  }, [executionTasks.length, selectedTaskIndex]);

  const selectedTask = executionTasks[selectedTaskIndex] ?? null;

  // Build analysis context for the AI chat panel
  const analysisContext: AnalysisContext | null = useMemo(() => {
    if (!selectedTask || !selectedExecutionId) return null;
    return {
      taskName: selectedTask.name || "",
      chipId: chipId,
      qid: qid,
      executionId: selectedExecutionId,
      taskId: selectedTask.task_id || "",
    };
  }, [selectedTask, selectedExecutionId, chipId, qid]);

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
        <span>
          No {metricName} history available for {qid} in the last 30 days
        </span>
      </div>
    );
  }

  // Column 1: Execution History
  const renderExecutionHistory = () => (
    <div className="flex flex-col min-h-0 h-full">
      <div className="mb-3 shrink-0">
        <div className="flex items-center gap-2 mb-1">
          <History className="h-4 w-4 text-primary" />
          <h3 className="text-sm font-bold text-base-content">
            Execution History
          </h3>
        </div>
        <p className="text-xs text-base-content/50">
          {executionGroups.length} executions with {metricName}
        </p>
      </div>
      <div className="flex-1 overflow-y-auto min-h-0">
        <div className="flex flex-col gap-2">
          {executionGroups.map((group, idx) => {
            // Find the metric item that matches the current metric name
            const metricItem =
              group.items.find((item) =>
                item.name?.toLowerCase().includes(metricName.toLowerCase()),
              ) || group.items[0];

            const isSelected = selectedExecutionId === group.executionId;

            return (
              <button
                key={group.executionId}
                onClick={() => {
                  setSelectedExecutionId(group.executionId);
                  setMobileTab("tasks");
                }}
                className={`w-full text-left p-3 rounded-lg transition-all border-2 ${
                  isSelected
                    ? "bg-primary text-primary-content border-primary"
                    : "bg-base-200 hover:bg-base-300 border-transparent hover:border-primary/30"
                }`}
              >
                <div className="flex justify-between items-start">
                  <div className="min-w-0 flex-1">
                    <div className="font-bold text-lg">
                      {formatMetricValue(metricItem?.value, metricUnit, 4)}{" "}
                      <span className="text-sm font-normal opacity-80">
                        {metricUnit}
                      </span>
                    </div>
                    <div className="text-xs opacity-70 mt-1">
                      {formatDateTimeCompact(group.timestamp)}
                    </div>
                    {metricItem?.name && (
                      <div className="text-xs opacity-60 mt-1 truncate">
                        {metricItem.name}
                      </div>
                    )}
                    {idx === 0 && (
                      <span
                        className={`badge badge-xs mt-1 ${
                          isSelected ? "badge-primary-content" : "badge-success"
                        }`}
                      >
                        Latest
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-1">
                    <span className="text-xs opacity-60">#{idx + 1}</span>
                    <ChevronRight
                      className={`h-4 w-4 opacity-40 ${isSelected ? "opacity-80" : ""}`}
                    />
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );

  // Column 2: Tasks in Execution
  const renderTasksList = () => (
    <div className="flex flex-col min-h-0 h-full">
      <div className="mb-3 shrink-0">
        <div className="flex items-center gap-2 mb-1">
          <ListTodo className="h-4 w-4 text-secondary" />
          <h3 className="text-sm font-bold text-base-content">
            Tasks in Execution
          </h3>
        </div>
        {selectedExecutionId && (
          <p className="text-[0.65rem] text-base-content/50 font-mono truncate">
            {selectedExecutionId}
          </p>
        )}
      </div>
      <div className="flex-1 overflow-y-auto min-h-0">
        {isExecutionLoading ? (
          <div className="flex items-center justify-center py-8">
            <span className="loading loading-spinner loading-md"></span>
          </div>
        ) : isExecutionError ? (
          <div className="text-sm text-error py-4">
            Failed to load execution
          </div>
        ) : executionTasks.length === 0 ? (
          <div className="text-center py-8">
            <ListTodo className="h-8 w-8 mx-auto text-base-content/30 mb-2" />
            <p className="text-sm text-base-content/50">
              No {metricName}-related tasks found for {qid}
            </p>
            <p className="text-xs text-base-content/40 mt-1">
              This execution may not include calibration for this qubit
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {executionTasks.map((task, idx) => {
              const isSelected = idx === selectedTaskIndex;
              const isMatchingMetric = task.name
                ?.toLowerCase()
                .includes(metricName.toLowerCase());

              return (
                <button
                  key={task.task_id || idx}
                  onClick={() => {
                    setSelectedTaskIndex(idx);
                    setMobileTab("details");
                  }}
                  className={`w-full text-left p-3 rounded-lg transition-all border-2 ${
                    isSelected
                      ? "bg-secondary text-secondary-content border-secondary"
                      : "bg-base-200 hover:bg-base-300 border-transparent hover:border-secondary/30"
                  }`}
                >
                  <div className="flex justify-between items-start">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-sm truncate">
                          {task.name || "Unnamed"}
                        </span>
                        {isMatchingMetric && (
                          <span
                            className={`badge badge-xs ${
                              isSelected
                                ? "badge-secondary-content"
                                : "badge-accent"
                            }`}
                          >
                            {metricName}
                          </span>
                        )}
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
                    <div className="flex items-center gap-1">
                      <span className="text-xs opacity-60">#{idx + 1}</span>
                      <ChevronRight
                        className={`h-4 w-4 opacity-40 ${isSelected ? "opacity-80" : ""}`}
                      />
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );

  // Column 3: Task Details
  const renderTaskDetails = () => (
    <div className="flex flex-col">
      <div className="flex items-center justify-between mb-3 shrink-0">
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-accent" />
          <h3 className="text-sm font-bold text-base-content">Task Details</h3>
        </div>
        {executionTasks.length > 0 && (
          <div className="text-xs text-base-content/60">
            {selectedTaskIndex + 1} / {executionTasks.length}
          </div>
        )}
      </div>

      {/* Navigation Arrows */}
      {executionTasks.length > 1 && (
        <div className="flex gap-2 mb-2 shrink-0">
          <button
            className="btn btn-xs btn-ghost"
            disabled={selectedTaskIndex === 0}
            onClick={() =>
              setSelectedTaskIndex((prev) => Math.max(0, prev - 1))
            }
          >
            ← Prev
          </button>
          <button
            className="btn btn-xs btn-ghost"
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

      {/* Figure Display - Fixed height with horizontal scroll */}
      <div className="h-[280px] bg-base-200 rounded-lg p-3 overflow-x-auto overflow-y-hidden flex items-center justify-start">
        {isExecutionLoading ? (
          <span className="loading loading-spinner loading-lg"></span>
        ) : !selectedTask ? (
          <div className="flex flex-col items-center justify-center text-base-content/40">
            <FileText className="h-12 w-12 mb-3 opacity-30" />
            <p className="text-sm">
              {selectedExecutionId
                ? `Select a task to view details`
                : "Select an execution first"}
            </p>
          </div>
        ) : selectedTask.figure_path ? (
          <TaskFigure
            path={selectedTask.figure_path}
            qid={qid}
            className="h-full w-auto object-contain"
          />
        ) : selectedTask.task_id ? (
          <TaskFigure
            taskId={selectedTask.task_id}
            qid={qid}
            className="h-full w-auto object-contain"
          />
        ) : (
          <div className="flex flex-col items-center justify-center text-base-content/40">
            <FileText className="h-12 w-12 mb-3 opacity-30" />
            <p className="text-sm">No figure available for this task</p>
          </div>
        )}
      </div>

      {/* Task Metadata */}
      {selectedTask && (
        <div className="mt-2 text-xs text-base-content/60 space-y-1 bg-base-200 p-3 rounded-lg">
          {selectedTask.name && (
            <div className="flex items-center gap-2">
              <span className="font-semibold">Task Name:</span>
              <span className="font-mono">{selectedTask.name}</span>
            </div>
          )}
          <div className="flex items-center gap-2">
            <span className="font-semibold">Execution ID:</span>
            <span className="font-mono truncate">{selectedExecutionId}</span>
          </div>
          {selectedTask.task_id && (
            <div className="flex items-center gap-2">
              <span className="font-semibold">Task ID:</span>
              <span className="font-mono truncate">{selectedTask.task_id}</span>
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
          {/* Metric Value from history if available */}
          {selectedGroup && selectedGroup.items.length > 0 && (
            <div className="flex items-center gap-2">
              <span className="font-semibold">Metric Value:</span>
              <span className="font-mono">
                {formatMetricValue(selectedGroup.items[0].value, metricUnit, 4)}{" "}
                {metricUnit}
              </span>
            </div>
          )}
          {/* Provenance link and Ask AI */}
          <div className="pt-2 mt-2 border-t border-base-300 flex items-center gap-2">
            <Link
              href={`/provenance?parameter=${encodeURIComponent(metricName)}&qid=${encodeURIComponent(qid)}&tab=lineage`}
              className="btn btn-xs btn-outline gap-1"
            >
              <GitBranch className="h-3 w-3" />
              View Provenance Lineage
            </Link>
            {analysisContext && (
              <button
                onClick={() => openAnalysisChat(analysisContext)}
                className="btn btn-xs btn-primary gap-1"
              >
                <Bot className="h-3 w-3" />
                Ask AI
              </button>
            )}
          </div>
        </div>
      )}

      {/* Input/Output Parameters */}
      {selectedTask && (
        <div className="flex flex-col gap-2 mt-2">
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
          {selectedTask.run_parameters &&
            Object.keys(selectedTask.run_parameters).length > 0 && (
              <ParametersTable
                title="Run Parameters"
                parameters={
                  selectedTask.run_parameters as Record<string, unknown>
                }
              />
            )}
        </div>
      )}

      {/* Issues */}
      {selectedTask?.task_id && (
        <TaskResultIssues taskId={selectedTask.task_id} />
      )}
    </div>
  );

  return (
    <div className="h-full min-h-0 flex flex-col">
      {/* Mobile Tabs */}
      <div className="lg:hidden mb-3 shrink-0">
        <div className="tabs tabs-boxed bg-base-200">
          <button
            className={`tab gap-1 ${mobileTab === "history" ? "tab-active" : ""}`}
            onClick={() => setMobileTab("history")}
          >
            <History className="h-3 w-3" />
            History
          </button>
          <button
            className={`tab gap-1 ${mobileTab === "tasks" ? "tab-active" : ""}`}
            onClick={() => setMobileTab("tasks")}
          >
            <ListTodo className="h-3 w-3" />
            Tasks
          </button>
          <button
            className={`tab gap-1 ${mobileTab === "details" ? "tab-active" : ""}`}
            onClick={() => setMobileTab("details")}
          >
            <FileText className="h-3 w-3" />
            Details
          </button>
        </div>
      </div>

      {/* Mobile Content */}
      <div className="lg:hidden flex-1 min-h-0 overflow-hidden">
        {mobileTab === "history" && renderExecutionHistory()}
        {mobileTab === "tasks" && renderTasksList()}
        {mobileTab === "details" && renderTaskDetails()}
      </div>

      {/* Desktop Layout */}
      <div className="hidden lg:flex gap-4 h-full min-h-0">
        {/* Column 1: Execution History */}
        <div className="w-1/4 flex flex-col min-h-0 border-r border-base-300 pr-4">
          {renderExecutionHistory()}
        </div>

        {/* Column 2: Tasks */}
        <div className="w-1/4 flex flex-col min-h-0 border-r border-base-300 pr-4">
          {renderTasksList()}
        </div>

        {/* Column 3: Details – scrollable */}
        <div className="w-1/2 overflow-y-auto min-h-0">
          {renderTaskDetails()}
        </div>
      </div>
    </div>
  );
}
