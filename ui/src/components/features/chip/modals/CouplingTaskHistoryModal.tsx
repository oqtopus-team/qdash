"use client";

import dynamic from "next/dynamic";
import React, { useState, useMemo, useCallback } from "react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { ChevronRight, History, FileText, GitBranch, Bot, ListTodo } from "lucide-react";

import type { TaskResult as Task } from "@/schemas";

import { formatDateTime, formatDateTimeCompact } from "@/lib/utils/datetime";
import { isChipMetricsQuery } from "@/lib/utils/queryInvalidation";

import { useGetExecution } from "@/client/execution/execution";
import { useGetCouplingTaskHistory } from "@/client/task-result/task-result";
import { useUpdateCalibrationParameters } from "@/client/calibration/calibration";
import { TaskFigure } from "@/components/charts/TaskFigure";
import {
  ExecutionHistoryModalContent,
  type ExecutionHistoryMobileTab,
} from "@/components/features/task-history/ExecutionHistoryModalContent";
import { ParametersTable } from "@/components/features/metrics/ParametersTable";
import { useManualOverrides } from "@/hooks/useManualOverrides";
import { TaskResultAiReviewNote } from "@/components/features/metrics/TaskResultAiReviewNote";
import { TaskResultIssues } from "@/components/features/metrics/TaskResultIssues";
import { TaskResultMemo } from "@/components/features/metrics/TaskResultMemo";
import type { AnalysisContext } from "@/hooks/useAnalysisChat";
import { useAnalysisChatContext } from "@/contexts/AnalysisChatContext";

const PlotlyRenderer = dynamic(
  () => import("@/components/charts/PlotlyRenderer").then((mod) => mod.PlotlyRenderer),
  { ssr: false },
);

interface CouplingTaskHistoryModalProps {
  chipId: string;
  couplingId: string;
  taskName: string;
  isOpen: boolean;
  onClose: () => void;
  selectedDate?: string;
}

export function CouplingTaskHistoryModal({
  chipId,
  couplingId,
  taskName,
  isOpen,
  onClose,
  selectedDate,
}: CouplingTaskHistoryModalProps) {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [selectedExecutionTaskIndex, setSelectedExecutionTaskIndex] = useState(0);
  const [viewMode, setViewMode] = useState<"static" | "interactive">("static");
  const [mobileTab, setMobileTab] = useState<ExecutionHistoryMobileTab>("history");
  const [saveMessage, setSaveMessage] = useState<{
    type: "success" | "error";
    text: string;
  } | null>(null);
  const { openMiniChat } = useAnalysisChatContext();
  const queryClient = useQueryClient();
  const updateParamsMutation = useUpdateCalibrationParameters();
  const manualOverrides = useManualOverrides(couplingId);

  const handleSaveParameters = useCallback(
    async (updatedParams: Record<string, unknown>) => {
      setSaveMessage(null);
      try {
        const res = await updateParamsMutation.mutateAsync({
          data: {
            chip_id: chipId,
            qid: couplingId,
            parameters: updatedParams as Record<string, Record<string, unknown>>,
          },
        });
        await queryClient.invalidateQueries({ predicate: isChipMetricsQuery });
        await queryClient.invalidateQueries({
          queryKey: [`/calibrations/manual-edits/${couplingId}`],
        });
        const count = res.data?.updated_count ?? 0;
        setSaveMessage({
          type: "success",
          text: `${count} parameter(s) saved`,
        });
        setTimeout(() => setSaveMessage(null), 5000);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to save";
        setSaveMessage({ type: "error", text: message });
      }
    },
    [chipId, couplingId, updateParamsMutation, queryClient],
  );

  const resolveQid = (taskQid: string, qidRole?: string): string => {
    if (!qidRole || qidRole === "self" || qidRole === "coupling") return taskQid;
    const match = taskQid.match(/^(\d+)-(\d+)$/);
    if (!match) return taskQid;
    const [, control, target] = match;
    if (qidRole === "control") return control;
    if (qidRole === "target") return target;
    return taskQid;
  };

  const buildProvenanceUrl = (parameterName: string, qidValue: string) => {
    const p = encodeURIComponent(parameterName);
    const q = encodeURIComponent(qidValue);
    return `/provenance?tab=lineage&parameter=${p}&qid=${q}`;
  };

  const { data, isLoading, isError } = useGetCouplingTaskHistory(
    couplingId,
    { chip_id: chipId, task: taskName },
    {
      query: {
        enabled: isOpen && !!chipId && !!couplingId && !!taskName,
        staleTime: 30000,
        gcTime: 60000,
      },
    },
  );

  const historyArray = useMemo(
    () =>
      Object.entries(data?.data?.data || {})
        .map(([key, task]) => ({ key, task: task as Task }))
        .sort((a, b) => {
          const dateA = a.task.end_at ? new Date(a.task.end_at).getTime() : 0;
          const dateB = b.task.end_at ? new Date(b.task.end_at).getTime() : 0;
          return dateB - dateA;
        }),
    [data],
  );

  React.useEffect(() => {
    if (!isOpen || historyArray.length === 0) return;
    if (!selectedDate || selectedDate === "latest") {
      setSelectedIndex(0);
      return;
    }
    const idx = historyArray.findIndex((item) => {
      if (!item.task.end_at) return false;
      const dateStr = formatDateTime(item.task.end_at, "yyyyMMdd");
      return dateStr === selectedDate;
    });
    setSelectedIndex(idx >= 0 ? idx : 0);
  }, [isOpen, historyArray, selectedDate]);

  const selectedItem = historyArray[selectedIndex];
  const selectedHistoryTask = selectedItem?.task;
  const selectedExecutionId = selectedHistoryTask?.execution_id ?? null;
  const { data: executionDetailData, isLoading: isExecutionLoading } = useGetExecution(
    selectedExecutionId || "",
    {
      query: {
        enabled: !!selectedExecutionId,
        staleTime: 30000,
        gcTime: 60000,
      },
    },
  );
  const executionTasks = useMemo(
    () => (executionDetailData?.data?.task ?? []).filter((task) => task.qid === couplingId),
    [executionDetailData?.data?.task, couplingId],
  );
  React.useEffect(() => {
    if (executionTasks.length === 0) {
      setSelectedExecutionTaskIndex(0);
      return;
    }
    const historyTaskId = selectedHistoryTask?.task_id;
    const matchingIndex = historyTaskId
      ? executionTasks.findIndex((task) => task.task_id === historyTaskId)
      : -1;
    setSelectedExecutionTaskIndex(matchingIndex >= 0 ? matchingIndex : 0);
  }, [executionTasks, selectedHistoryTask?.task_id]);
  React.useEffect(() => {
    if (executionTasks.length > 0 && selectedExecutionTaskIndex >= executionTasks.length) {
      setSelectedExecutionTaskIndex(0);
    }
  }, [executionTasks.length, selectedExecutionTaskIndex]);
  const selectedTask = executionTasks[selectedExecutionTaskIndex] ?? selectedHistoryTask;
  const figures = selectedTask
    ? Array.isArray(selectedTask.figure_path)
      ? selectedTask.figure_path
      : selectedTask.figure_path
        ? [selectedTask.figure_path]
        : []
    : [];
  const jsonFigures = selectedTask
    ? Array.isArray(selectedTask.json_figure_path)
      ? selectedTask.json_figure_path
      : selectedTask.json_figure_path
        ? [selectedTask.json_figure_path]
        : []
    : [];
  const hasJsonFigures = jsonFigures.length > 0;

  const analysisContext: AnalysisContext | null = useMemo(() => {
    if (!selectedTask?.task_id) return null;
    return {
      taskName: selectedTask.name || taskName,
      chipId,
      qid: couplingId,
      executionId: selectedExecutionId || "",
      taskId: selectedTask.task_id,
    };
  }, [selectedTask, selectedExecutionId, chipId, couplingId, taskName]);

  const handleSelectIndex = (idx: number) => {
    setSelectedIndex(idx);
    setViewMode("static");
    setMobileTab("tasks");
  };

  const handleSelectExecutionTask = (idx: number) => {
    setSelectedExecutionTaskIndex(idx);
    setViewMode("static");
    setMobileTab("details");
  };

  // Column 1: Execution History
  const renderHistoryList = () => (
    <div className="flex flex-col min-h-0 h-full">
      <div className="mb-3 shrink-0">
        <div className="flex items-center gap-2 mb-1">
          <History className="h-4 w-4 text-primary" />
          <h3 className="text-sm font-bold text-base-content">Execution History</h3>
        </div>
        <p className="text-xs text-base-content/50">
          {historyArray.length} executions with {taskName}
        </p>
      </div>
      <div className="flex-1 overflow-y-auto min-h-0">
        <div className="flex flex-col gap-2">
          {historyArray.map((item, idx) => {
            const isSelected = idx === selectedIndex;
            return (
              <button
                key={item.key}
                onClick={() => handleSelectIndex(idx)}
                className={`w-full text-left p-3 rounded-lg transition-all border-2 ${
                  isSelected
                    ? "bg-primary text-primary-content border-primary"
                    : "bg-base-200 hover:bg-base-300 border-transparent hover:border-primary/30"
                }`}
              >
                <div className="flex justify-between items-start">
                  <div className="min-w-0 flex-1">
                    <div className="font-bold text-lg">
                      {item.task.status === "completed" ? (
                        <span className={isSelected ? "" : "text-success"}>Completed</span>
                      ) : item.task.status === "failed" ? (
                        <span className={isSelected ? "" : "text-error"}>Failed</span>
                      ) : (
                        <span className={isSelected ? "" : "text-warning"}>{item.task.status}</span>
                      )}
                    </div>
                    <div className="text-xs opacity-70 mt-1">
                      {item.task.end_at ? formatDateTimeCompact(item.task.end_at) : "N/A"}
                    </div>
                    {item.task.name && (
                      <div className="text-xs opacity-60 mt-1 truncate">{item.task.name}</div>
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
          <h3 className="text-sm font-bold text-base-content">Tasks in Execution</h3>
        </div>
        {selectedExecutionId ? (
          <p className="text-[0.65rem] text-base-content/50 font-mono truncate">
            {selectedExecutionId}
          </p>
        ) : null}
      </div>
      <div className="flex-1 overflow-y-auto min-h-0">
        {isExecutionLoading ? (
          <div className="flex items-center justify-center py-8">
            <span className="loading loading-spinner loading-md"></span>
          </div>
        ) : executionTasks.length === 0 ? (
          <div className="text-center py-8">
            <ListTodo className="h-8 w-8 mx-auto text-base-content/30 mb-2" />
            <p className="text-sm text-base-content/50">
              No {taskName}-related tasks found for {couplingId}
            </p>
            <p className="text-xs text-base-content/40 mt-1">
              This execution may not include calibration for this coupling
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {executionTasks.map((task, idx) => {
              const isSelected = task.task_id === selectedTask?.task_id;
              const isMatchingTask = task.name?.toLowerCase().includes(taskName.toLowerCase());
              return (
                <button
                  key={task.task_id || `${task.name}-${idx}`}
                  onClick={() => handleSelectExecutionTask(idx)}
                  className={`w-full text-left p-3 rounded-lg transition-all border-2 ${
                    isSelected
                      ? "bg-secondary text-secondary-content border-secondary"
                      : "bg-base-200 hover:bg-base-300 border-transparent hover:border-secondary/30"
                  }`}
                >
                  <div className="flex justify-between items-start">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-sm truncate">{task.name || "Unnamed"}</span>
                        {isMatchingTask && (
                          <span
                            className={`badge badge-xs ${
                              isSelected ? "badge-secondary-content" : "badge-accent"
                            }`}
                          >
                            {taskName}
                          </span>
                        )}
                      </div>
                      <div className="text-xs opacity-70 mt-1">
                        {task.start_at ? formatDateTimeCompact(String(task.start_at)) : ""}
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
        {executionTasks.length > 0 ? (
          <div className="text-xs text-base-content/60">
            {selectedExecutionTaskIndex + 1} / {executionTasks.length}
          </div>
        ) : historyArray.length > 0 ? (
          <div className="text-xs text-base-content/60">
            {selectedIndex + 1} / {historyArray.length}
          </div>
        ) : null}
      </div>

      {/* Navigation Arrows */}
      {executionTasks.length > 1 && (
        <div className="flex gap-2 mb-2 shrink-0">
          <button
            className="btn btn-xs btn-ghost"
            disabled={selectedExecutionTaskIndex === 0}
            onClick={() => handleSelectExecutionTask(Math.max(0, selectedExecutionTaskIndex - 1))}
          >
            ← Prev
          </button>
          <button
            className="btn btn-xs btn-ghost"
            disabled={selectedExecutionTaskIndex === executionTasks.length - 1}
            onClick={() =>
              handleSelectExecutionTask(
                Math.min(executionTasks.length - 1, selectedExecutionTaskIndex + 1),
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
              {selectedExecutionId ? "Select a task to view details" : "Select an execution first"}
            </p>
          </div>
        ) : viewMode === "interactive" && hasJsonFigures ? (
          jsonFigures.map((jf, i) => (
            <div
              key={i}
              className="min-h-[250px] min-w-[400px] flex-shrink-0 flex justify-center items-center"
            >
              <PlotlyRenderer
                className="w-full h-full"
                fullPath={`/api/executions/figure?path=${encodeURIComponent(jf)}`}
              />
            </div>
          ))
        ) : figures.length > 0 ? (
          figures.map((fig, i) => (
            <TaskFigure
              key={i}
              path={fig}
              qid={couplingId}
              className="h-full w-auto object-contain"
            />
          ))
        ) : selectedTask.task_id ? (
          <TaskFigure
            taskId={selectedTask.task_id}
            qid={couplingId}
            className="h-full w-auto object-contain"
          />
        ) : (
          <div className="flex flex-col items-center justify-center text-base-content/40">
            <FileText className="h-12 w-12 mb-3 opacity-30" />
            <p className="text-sm">No figure available for this task</p>
          </div>
        )}
      </div>

      {/* View mode toggle (static / interactive) */}
      {hasJsonFigures && (
        <div className="flex justify-center mt-2 gap-2 items-center">
          {viewMode === "static" ? (
            <button className="btn btn-xs btn-primary" onClick={() => setViewMode("interactive")}>
              Interactive
            </button>
          ) : (
            <button className="btn btn-xs btn-ghost" onClick={() => setViewMode("static")}>
              Static
            </button>
          )}
        </div>
      )}

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
              <span className="font-semibold">Start:</span>
              <span>{formatDateTime(String(selectedTask.start_at))}</span>
            </div>
          )}
          {selectedTask.end_at && (
            <div className="flex items-center gap-2">
              <span className="font-semibold">End:</span>
              <span>{formatDateTime(String(selectedTask.end_at))}</span>
            </div>
          )}
          {/* Provenance link and Ask AI */}
          <div className="pt-2 mt-2 border-t border-base-300 flex items-center gap-2 flex-wrap">
            <Link
              href={(() => {
                const outputs = selectedTask.output_parameters
                  ? Object.entries(selectedTask.output_parameters)
                  : [];
                const inputs = selectedTask.input_parameters
                  ? Object.entries(selectedTask.input_parameters)
                  : [];
                const [key, paramValue] =
                  (outputs[0] as [string, Record<string, unknown>] | undefined) ??
                  (inputs[0] as [string, Record<string, unknown>] | undefined) ??
                  [];
                if (key && paramValue) {
                  const pv = paramValue as Record<string, unknown>;
                  const parameterName = (pv?.parameter_name as string | undefined) || key;
                  const resolvedQid = resolveQid(couplingId, pv?.qid_role as string | undefined);
                  return buildProvenanceUrl(parameterName, resolvedQid);
                }
                return "/provenance";
              })()}
              className="btn btn-xs btn-outline gap-1"
            >
              <GitBranch className="h-3 w-3" />
              View Provenance Lineage
            </Link>
            {analysisContext && (
              <button
                onClick={() => openMiniChat(analysisContext)}
                className="btn btn-xs btn-primary gap-1"
              >
                <Bot className="h-3 w-3" />
                Ask AI
              </button>
            )}
          </div>
        </div>
      )}

      {selectedTask?.task_id && (
        <TaskResultAiReviewNote taskId={selectedTask.task_id} hideWhenEmpty />
      )}
      {selectedTask?.task_id && (
        <TaskResultMemo taskId={selectedTask.task_id} chipId={chipId} hideWhenEmpty />
      )}

      {/* Parameters */}
      {selectedTask && (
        <div className="flex flex-col gap-2 mt-2">
          {selectedTask.input_parameters &&
            Object.keys(selectedTask.input_parameters).length > 0 && (
              <ParametersTable
                title="Input Parameters"
                parameters={selectedTask.input_parameters as Record<string, unknown>}
              />
            )}
          {selectedTask.output_parameters &&
            Object.keys(selectedTask.output_parameters).length > 0 && (
              <>
                <ParametersTable
                  title="Output Parameters"
                  parameters={selectedTask.output_parameters as Record<string, unknown>}
                  editable
                  onSave={handleSaveParameters}
                  isSaving={updateParamsMutation.isPending}
                  overrides={manualOverrides}
                />
                {saveMessage && (
                  <div
                    className={`text-xs px-2 py-1 rounded ${
                      saveMessage.type === "success"
                        ? "text-success bg-success/10"
                        : "text-error bg-error/10"
                    }`}
                  >
                    {saveMessage.text}
                  </div>
                )}
              </>
            )}
          {selectedTask.run_parameters && Object.keys(selectedTask.run_parameters).length > 0 && (
            <ParametersTable
              title="Run Parameters"
              parameters={selectedTask.run_parameters as Record<string, unknown>}
            />
          )}
        </div>
      )}

      {/* Issues */}
      {selectedTask?.task_id && <TaskResultIssues taskId={selectedTask.task_id} />}
    </div>
  );

  if (!isOpen) return null;

  return (
    <div
      className="modal modal-open modal-bottom sm:modal-middle"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="modal-box w-full sm:w-11/12 max-w-[112rem] h-[90vh] sm:h-[95vh] bg-base-100 p-0 overflow-hidden flex flex-col"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="px-4 sm:px-6 py-3 sm:py-4 border-b border-base-300 flex items-center justify-between">
          <div className="min-w-0 flex-1">
            <h2 className="text-lg sm:text-2xl font-bold truncate">{taskName}</h2>
            <p className="text-sm sm:text-base text-base-content/70 mt-0.5 sm:mt-1">
              Coupling {couplingId}
            </p>
          </div>
          <button onClick={onClose} className="btn btn-sm btn-circle btn-ghost flex-shrink-0">
            ✕
          </button>
        </div>

        <div className="flex-1 min-h-0 overflow-hidden p-3 sm:p-6">
          {isLoading ? (
            <div className="flex items-center justify-center h-48 sm:h-96">
              <span className="loading loading-spinner loading-lg"></span>
            </div>
          ) : isError || historyArray.length === 0 ? (
            <div className="alert alert-info text-sm">
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
                  d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              <span>No history available</span>
            </div>
          ) : (
            <ExecutionHistoryModalContent
              mobileTab={mobileTab}
              onMobileTabChange={setMobileTab}
              history={renderHistoryList()}
              tasks={renderTasksList()}
              details={renderTaskDetails()}
            />
          )}
        </div>
      </div>
    </div>
  );
}
