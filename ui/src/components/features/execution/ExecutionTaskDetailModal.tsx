"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Bot, ChevronRight, FileText, GitBranch, History, ListTodo } from "lucide-react";

import type { Task } from "@/schemas";

import { TaskFigure } from "@/components/charts/TaskFigure";
import {
  ExecutionHistoryModalContent,
  type ExecutionHistoryMobileTab,
} from "@/components/features/task-history/ExecutionHistoryModalContent";
import { ParametersTable } from "@/components/features/metrics/ParametersTable";
import { TaskResultAiReviewNote } from "@/components/features/metrics/TaskResultAiReviewNote";
import { TaskResultIssues } from "@/components/features/metrics/TaskResultIssues";
import { TaskResultMemo } from "@/components/features/metrics/TaskResultMemo";
import { useAnalysisChatContext } from "@/contexts/AnalysisChatContext";
import type { AnalysisContext } from "@/hooks/useAnalysisChat";
import { formatDateTime, formatDateTimeCompact } from "@/lib/utils/datetime";

interface ExecutionTaskDetailModalProps {
  isOpen: boolean;
  chipId: string;
  executionId: string;
  executionName?: string;
  qid: string;
  tasks: Task[];
  onClose: () => void;
}

function statusBadgeClass(status?: string | null) {
  if (status === "completed") return "badge-success";
  if (status === "failed") return "badge-error";
  if (status === "cancelled") return "badge-neutral";
  return "badge-warning";
}

function resolveQid(taskQid: string, qidRole?: string): string {
  if (!qidRole || qidRole === "self" || qidRole === "coupling") return taskQid;
  const match = taskQid.match(/^(\d+)-(\d+)$/);
  if (!match) return taskQid;
  const [, control, target] = match;
  if (qidRole === "control") return control;
  if (qidRole === "target") return target;
  return taskQid;
}

function buildProvenanceUrl(parameterName: string, qidValue: string) {
  const parameter = encodeURIComponent(parameterName);
  const encodedQid = encodeURIComponent(qidValue);
  return `/provenance?tab=lineage&parameter=${parameter}&qid=${encodedQid}`;
}

export function ExecutionTaskDetailModal({
  isOpen,
  chipId,
  executionId,
  executionName,
  qid,
  tasks,
  onClose,
}: ExecutionTaskDetailModalProps) {
  const [selectedTaskIndex, setSelectedTaskIndex] = useState(0);
  const [mobileTab, setMobileTab] = useState<ExecutionHistoryMobileTab>("tasks");
  const { openMiniChat } = useAnalysisChatContext();

  const selectedTask = tasks[selectedTaskIndex] ?? null;

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

  const analysisContext: AnalysisContext | null = useMemo(() => {
    if (!selectedTask?.task_id) return null;
    return {
      taskName: selectedTask.name || "",
      chipId,
      qid,
      executionId,
      taskId: selectedTask.task_id,
    };
  }, [selectedTask, chipId, qid, executionId]);

  const handleSelectTask = (idx: number) => {
    setSelectedTaskIndex(idx);
    setMobileTab("details");
  };

  if (!isOpen) return null;

  const renderExecutionHistory = () => (
    <div className="flex flex-col min-h-0 h-full">
      <div className="mb-3 shrink-0">
        <div className="flex items-center gap-2 mb-1">
          <History className="h-4 w-4 text-primary" />
          <h3 className="text-sm font-bold text-base-content">Execution History</h3>
        </div>
        <p className="text-xs text-base-content/50">Current execution</p>
      </div>
      <div className="flex-1 overflow-y-auto min-h-0">
        <button className="w-full text-left p-3 rounded-lg transition-all border-2 bg-primary text-primary-content border-primary">
          <div className="flex justify-between items-start">
            <div className="min-w-0 flex-1">
              <div className="font-bold text-lg truncate">{executionName || "Execution"}</div>
              <div className="text-xs opacity-70 mt-1 font-mono truncate">{executionId}</div>
              <span className="badge badge-xs mt-1 badge-primary-content">Current</span>
            </div>
            <ChevronRight className="h-4 w-4 opacity-80" />
          </div>
        </button>
      </div>
    </div>
  );

  const renderTasksList = () => (
    <div className="flex flex-col min-h-0 h-full">
      <div className="mb-3 shrink-0">
        <div className="flex items-center gap-2 mb-1">
          <ListTodo className="h-4 w-4 text-secondary" />
          <h3 className="text-sm font-bold text-base-content">Tasks in Execution</h3>
        </div>
        <p className="text-[0.65rem] text-base-content/50 font-mono truncate">{executionId}</p>
      </div>
      <div className="flex-1 overflow-y-auto min-h-0">
        {tasks.length === 0 ? (
          <div className="text-center py-8">
            <ListTodo className="h-8 w-8 mx-auto text-base-content/30 mb-2" />
            <p className="text-sm text-base-content/50">No tasks found for {qid}</p>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {tasks.map((task, idx) => {
              const isSelected = idx === selectedTaskIndex;
              return (
                <button
                  key={task.task_id || `${task.name}-${idx}`}
                  onClick={() => handleSelectTask(idx)}
                  className={`w-full text-left p-3 rounded-lg transition-all border-2 ${
                    isSelected
                      ? "bg-secondary text-secondary-content border-secondary"
                      : "bg-base-200 hover:bg-base-300 border-transparent hover:border-secondary/30"
                  }`}
                >
                  <div className="flex justify-between items-start">
                    <div className="min-w-0 flex-1">
                      <div className="font-bold text-sm truncate">{task.name || "Unnamed"}</div>
                      <div className="text-xs opacity-70 mt-1">
                        {task.start_at ? formatDateTimeCompact(String(task.start_at)) : ""}
                      </div>
                      <span className={`badge badge-xs mt-1 ${statusBadgeClass(task.status)}`}>
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

  const renderTaskDetails = () => (
    <div className="flex flex-col">
      <div className="flex items-center justify-between mb-3 shrink-0">
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-accent" />
          <h3 className="text-sm font-bold text-base-content">Task Details</h3>
        </div>
        {tasks.length > 0 && (
          <div className="text-xs text-base-content/60">
            {selectedTaskIndex + 1} / {tasks.length}
          </div>
        )}
      </div>

      {tasks.length > 1 && (
        <div className="flex gap-2 mb-2 shrink-0">
          <button
            className="btn btn-xs btn-ghost"
            disabled={selectedTaskIndex === 0}
            onClick={() => handleSelectTask(Math.max(0, selectedTaskIndex - 1))}
          >
            ← Prev
          </button>
          <button
            className="btn btn-xs btn-ghost"
            disabled={selectedTaskIndex === tasks.length - 1}
            onClick={() => handleSelectTask(Math.min(tasks.length - 1, selectedTaskIndex + 1))}
          >
            Next →
          </button>
        </div>
      )}

      <div className="h-[280px] bg-base-200 rounded-lg p-3 overflow-x-auto overflow-y-hidden flex items-center justify-start">
        {!selectedTask ? (
          <div className="flex flex-col items-center justify-center text-base-content/40">
            <FileText className="h-12 w-12 mb-3 opacity-30" />
            <p className="text-sm">Select a task to view details</p>
          </div>
        ) : figures.length > 0 ? (
          figures.map((figure, idx) => (
            <TaskFigure
              key={idx}
              path={figure}
              jsonFigurePath={jsonFigures[idx]}
              qid={qid}
              className="h-full w-auto object-contain"
            />
          ))
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
            <span className="font-mono truncate">{executionId}</span>
          </div>
          {selectedTask.task_id && (
            <div className="flex items-center gap-2">
              <span className="font-semibold">Task ID:</span>
              <Link
                href={`/task-results/${selectedTask.task_id}`}
                className="font-mono truncate link link-primary"
              >
                {selectedTask.task_id}
              </Link>
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
                  const parameterName = (paramValue?.parameter_name as string | undefined) || key;
                  const resolvedQid = resolveQid(qid, paramValue?.qid_role as string | undefined);
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
              <ParametersTable
                title="Output Parameters"
                parameters={selectedTask.output_parameters as Record<string, unknown>}
              />
            )}
          {selectedTask.run_parameters && Object.keys(selectedTask.run_parameters).length > 0 && (
            <ParametersTable
              title="Run Parameters"
              parameters={selectedTask.run_parameters as Record<string, unknown>}
            />
          )}
        </div>
      )}

      {selectedTask?.task_id && <TaskResultIssues taskId={selectedTask.task_id} />}
    </div>
  );

  return (
    <div
      className="modal modal-open modal-bottom sm:modal-middle"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        className="modal-box w-full sm:w-11/12 max-w-[112rem] h-[90vh] sm:h-[95vh] bg-base-100 p-0 overflow-hidden flex flex-col"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="px-4 sm:px-6 py-3 sm:py-4 border-b border-base-300 flex items-center justify-between">
          <div className="min-w-0 flex-1">
            <h2 className="text-lg sm:text-2xl font-bold truncate">
              {selectedTask?.name || "Task Details"}
            </h2>
            <p className="text-sm sm:text-base text-base-content/70 mt-0.5 sm:mt-1">
              {qid.includes("-") ? "Coupling" : "QID"} {qid}
            </p>
          </div>
          <button onClick={onClose} className="btn btn-sm btn-circle btn-ghost flex-shrink-0">
            ✕
          </button>
        </div>

        <div className="flex-1 min-h-0 overflow-hidden p-3 sm:p-6">
          <ExecutionHistoryModalContent
            mobileTab={mobileTab}
            onMobileTabChange={setMobileTab}
            history={renderExecutionHistory()}
            tasks={renderTasksList()}
            details={renderTaskDetails()}
          />
        </div>
      </div>
    </div>
  );
}
