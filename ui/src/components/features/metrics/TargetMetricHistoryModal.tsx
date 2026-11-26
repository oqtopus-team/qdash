"use client";

import { useState, useMemo, useEffect, type ReactNode } from "react";

import { ChevronRight, GitBranch, History, FileText } from "lucide-react";

import { useGetExecution } from "@/client/execution/execution";
import { TaskFigure } from "@/components/charts/TaskFigure";
import {
  ExecutionHistoryModalContent,
  type ExecutionHistoryMobileTab,
} from "@/components/features/task-history/ExecutionHistoryModalContent";
import { formatDateTime, formatDateTimeCompact } from "@/lib/utils/datetime";
import { useManualOverrides } from "@/hooks/useManualOverrides";

import { LineageButton } from "@/components/features/provenance/ParameterLineageDialog";
import { TaskResultEvaluations } from "@/components/features/evaluations/TaskResultEvaluations";
import { TaskResultThreads } from "@/components/features/forum/TaskResultThreads";
import { TaskResultMemo } from "./TaskResultMemo";
import { TaskResultExcludeButton } from "./TaskResultExcludeButton";
import type { TaskChatContext } from "@/types/agentChat";
import type { MetricHistoryItem } from "./MetricHistoryView";
import { useChatDock } from "@/contexts/ChatDockContext";
import {
  ExecutionTasksColumn,
  TaskDetailsHeader,
  TaskParametersTables,
} from "@/components/features/task-history/TaskResultDetailParts";

type MetricHistoryTargetKind = "qubit" | "coupling";

interface MetricHistoryQueryState {
  history: MetricHistoryItem[] | undefined;
  isLoading: boolean;
  isError: boolean;
}

interface TargetMetricHistoryModalProps {
  chipId: string;
  /** Qubit ID or (direction-resolved) coupling ID the history belongs to. */
  targetId: string;
  targetKind: MetricHistoryTargetKind;
  metricName: string;
  metricUnit: string;
  startAt?: string | null;
  endAt?: string | null;
  query: MetricHistoryQueryState;
  /** Controls shown above every state, such as the coupling direction toggle. */
  topContent?: ReactNode;
  /** Changing this value clears the selection, such as on a coupling direction toggle. */
  selectionResetKey?: string;
}

interface ExecutionGroup {
  executionId: string;
  timestamp: string;
  items: MetricHistoryItem[];
}

function formatMetricValue(value: number | null, unit: string, precision: number = 2): string {
  if (value === null || value === undefined) return "N/A";
  const displayValue = unit === "%" ? value * 100 : value;
  return displayValue.toFixed(precision);
}

/**
 * History of a qubit or coupling metric, with the selected execution's task details.
 *
 * The selection is kept when `targetId` changes and cleared only when `selectionResetKey`
 * changes.
 */
export function TargetMetricHistoryModal({
  chipId,
  targetId: qid,
  targetKind,
  metricName,
  metricUnit,
  startAt,
  endAt,
  query: { history: rawHistory, isLoading, isError },
  topContent,
  selectionResetKey,
}: TargetMetricHistoryModalProps) {
  const [selectedExecutionId, setSelectedExecutionId] = useState<string | null>(null);
  const [selectedTaskIndex, setSelectedTaskIndex] = useState(0);
  const [mobileTab, setMobileTab] = useState<ExecutionHistoryMobileTab>("history");
  const [appliedResetKey, setAppliedResetKey] = useState(selectionResetKey);
  if (appliedResetKey !== selectionResetKey) {
    setAppliedResetKey(selectionResetKey);
    setSelectedExecutionId(null);
    setSelectedTaskIndex(0);
  }
  const { openMiniChat } = useChatDock();
  const manualOverrides = useManualOverrides(qid);
  // The coupling modal predates result notes; only the qubit modal shows them.
  const showsMemo = targetKind === "qubit";

  const history = useMemo(() => rawHistory || [], [rawHistory]);

  // When caller passes a date range (e.g. absolute mode on metrics page),
  // restrict the Execution History to items whose timestamp falls inside it.
  const filteredHistory = useMemo(() => {
    if (!startAt && !endAt) return history;
    const startMs = startAt ? new Date(startAt).getTime() : -Infinity;
    const endMs = endAt ? new Date(endAt).getTime() : Infinity;
    return history.filter((item) => {
      const ts = new Date(item.timestamp).getTime();
      return ts >= startMs && ts <= endMs;
    });
  }, [history, startAt, endAt]);

  // Group history items by execution_id
  const executionGroups = useMemo(() => {
    const groups = new Map<string, ExecutionGroup>();
    filteredHistory.forEach((item) => {
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
      (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
    );
  }, [filteredHistory]);

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

  const selectedGroup = executionGroups.find((g) => g.executionId === selectedExecutionId);

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
        const matchingIndex = executionTasks.findIndex((task) => task.task_id === historyTaskId);
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
    if (selectedTaskIndex >= executionTasks.length && executionTasks.length > 0) {
      setSelectedTaskIndex(0);
    }
  }, [executionTasks.length, selectedTaskIndex]);

  const selectedTask = executionTasks[selectedTaskIndex] ?? null;

  // Find the metric history item that corresponds to the selected task,
  // so the exclude button knows which task_id to flag and shows current state.
  const selectedHistoryItem = useMemo(() => {
    if (!selectedGroup) return null;
    const taskId = selectedTask?.task_id;
    if (taskId) {
      const exact = selectedGroup.items.find((it) => it.task_id === taskId);
      if (exact) return exact;
    }
    return selectedGroup.items[0] ?? null;
  }, [selectedGroup, selectedTask?.task_id]);

  // The task result this chat is about
  const chatContext: TaskChatContext | null = useMemo(() => {
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
    const spinner = (
      <div className="flex items-center justify-center h-96">
        <span className="loading loading-spinner loading-lg"></span>
      </div>
    );
    return topContent ? (
      <div>
        <div className="mb-3">{topContent}</div>
        {spinner}
      </div>
    ) : (
      spinner
    );
  }

  if (isError || filteredHistory.length === 0) {
    const alert = (
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
          No {metricName} history available for {qid}
          {startAt || endAt ? " in the selected date range" : " in the last 365 days"}
        </span>
      </div>
    );
    return topContent ? (
      <div className="space-y-3">
        <div>{topContent}</div>
        {alert}
      </div>
    ) : (
      alert
    );
  }

  // Column 1: Execution History
  const renderExecutionHistory = () => (
    <div className="flex flex-col min-h-0 h-full">
      <div className="mb-3 shrink-0">
        <div className="flex items-center gap-2 mb-1">
          <History className="h-4 w-4 text-primary" />
          <h3 className="text-sm font-medium text-base-content">Execution History</h3>
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

            const isExcluded = Boolean(metricItem?.excluded);

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
                } ${isExcluded ? "opacity-60" : ""}`}
              >
                <div className="flex justify-between items-start">
                  <div className="min-w-0 flex-1">
                    <div className={`font-medium text-sm ${isExcluded ? "line-through" : ""}`}>
                      {formatMetricValue(metricItem?.value, metricUnit, 4)}{" "}
                      <span className="text-sm font-normal opacity-80">{metricUnit}</span>
                    </div>
                    <div className="text-xs opacity-70 mt-1">
                      {formatDateTimeCompact(group.timestamp)}
                    </div>
                    {metricItem?.name && (
                      <div className="text-xs opacity-60 mt-1 truncate">{metricItem.name}</div>
                    )}
                    <div className="flex flex-wrap items-center gap-1 mt-1">
                      {idx === 0 && (
                        <span
                          className={`badge badge-xs ${
                            isSelected ? "badge-primary-content" : "badge-success"
                          }`}
                        >
                          Latest
                        </span>
                      )}
                      {isExcluded && (
                        <span className="badge badge-xs badge-warning gap-1">Excluded</span>
                      )}
                    </div>
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
    <ExecutionTasksColumn
      executionId={selectedExecutionId}
      tasks={executionTasks}
      isLoading={isExecutionLoading}
      isError={isExecutionError}
      isSelected={(_task, idx) => idx === selectedTaskIndex}
      onSelect={(idx) => {
        setSelectedTaskIndex(idx);
        setMobileTab("details");
      }}
      matchName={metricName}
      targetId={qid}
      targetNoun={targetKind}
    />
  );

  // Column 3: Task Details
  const renderTaskDetails = () => (
    <div className="flex flex-col">
      <TaskDetailsHeader
        position={
          executionTasks.length > 0 ? `${selectedTaskIndex + 1} / ${executionTasks.length}` : null
        }
        index={selectedTaskIndex}
        total={executionTasks.length}
        onSelect={setSelectedTaskIndex}
      />

      {/* Figure Display - Fixed height with horizontal scroll */}
      <div className="h-[280px] bg-base-200 rounded-lg p-3 overflow-x-auto overflow-y-hidden flex items-center justify-start">
        {isExecutionLoading ? (
          <span className="loading loading-spinner loading-lg"></span>
        ) : !selectedTask ? (
          <div className="flex flex-col items-center justify-center text-base-content/40">
            <FileText className="h-12 w-12 mb-3 opacity-30" />
            <p className="text-sm">
              {selectedExecutionId ? `Select a task to view details` : "Select an execution first"}
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
              <span className="font-medium">Task Name:</span>
              <span className="font-mono">{selectedTask.name}</span>
            </div>
          )}
          <div className="flex items-center gap-2">
            <span className="font-medium">Execution ID:</span>
            <span className="font-mono truncate">{selectedExecutionId}</span>
          </div>
          {selectedTask.task_id && (
            <div className="flex items-center gap-2">
              <span className="font-medium">Task ID:</span>
              <a
                href={`/task-results/${selectedTask.task_id}`}
                className="font-mono truncate link link-primary"
              >
                {selectedTask.task_id}
              </a>
            </div>
          )}
          {selectedTask.start_at != null && (
            <div className="flex items-center gap-2">
              <span className="font-medium">Start:</span>
              <span>{formatDateTime(String(selectedTask.start_at))}</span>
            </div>
          )}
          {selectedTask.end_at != null && (
            <div className="flex items-center gap-2">
              <span className="font-medium">End:</span>
              <span>{formatDateTime(String(selectedTask.end_at))}</span>
            </div>
          )}
          {/* Metric Value from history if available */}
          {selectedGroup && selectedGroup.items.length > 0 && (
            <div className="flex items-center gap-2">
              <span className="font-medium">Metric Value:</span>
              <span className="font-mono">
                {formatMetricValue(selectedGroup.items[0].value, metricUnit, 4)} {metricUnit}
              </span>
            </div>
          )}
          {/* Lineage */}
          <div className="pt-2 mt-2 border-t border-base-300 flex items-center gap-2 flex-wrap">
            <LineageButton
              target={{ parameterName: metricName, qid: qid }}
              className="btn btn-xs btn-outline"
            >
              <GitBranch data-icon="inline-start" />
              Lineage
            </LineageButton>
            {selectedHistoryItem?.task_id && (
              <TaskResultExcludeButton
                taskId={selectedHistoryItem.task_id}
                excluded={Boolean(selectedHistoryItem.excluded)}
                excludedReason={selectedHistoryItem.excluded_reason}
                excludedBy={selectedHistoryItem.excluded_by}
                excludedAt={selectedHistoryItem.excluded_at}
              />
            )}
          </div>
        </div>
      )}

      {/* Input/Output Parameters */}
      {selectedTask && (
        <TaskParametersTables
          task={selectedTask}
          outputOverrides={manualOverrides}
          className={`flex flex-col gap-2 mt-2 ${showsMemo ? "" : "mb-6"}`}
        />
      )}

      {/* Notes (above threads) */}
      {showsMemo && selectedTask?.task_id && (
        <TaskResultMemo taskId={selectedTask.task_id} chipId={chipId} />
      )}

      {/* Forum threads about this result */}
      {/* AI evaluations of this result, requested the same way as from the chip page */}
      {selectedTask?.task_id && (
        <TaskResultEvaluations
          taskId={selectedTask.task_id}
          chipId={chipId}
          taskName={selectedTask.name || undefined}
          qid={qid}
          executionId={selectedExecutionId || undefined}
          onChat={chatContext ? () => openMiniChat(chatContext) : undefined}
        />
      )}

      {selectedTask?.task_id && <TaskResultThreads taskId={selectedTask.task_id} />}
    </div>
  );

  return (
    <ExecutionHistoryModalContent
      mobileTab={mobileTab}
      onMobileTabChange={setMobileTab}
      history={renderExecutionHistory()}
      tasks={renderTasksList()}
      details={renderTaskDetails()}
      topContent={topContent}
    />
  );
}
