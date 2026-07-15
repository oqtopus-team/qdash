"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import {
  AlertCircle,
  CheckCircle2,
  ChevronRight,
  Clock3,
  ExternalLink,
  FileText,
  HelpCircle,
  History,
} from "lucide-react";

import type { Task } from "@/schemas";

import { useGetQubitTaskHistory } from "@/client/task-result/task-result";
import { TaskFigure } from "@/components/charts/TaskFigure";
import { ReanalysisPanel } from "@/components/features/qubit/ReanalysisPanel";
import { formatDateTime } from "@/lib/utils/datetime";

const REANALYZABLE_TASKS = new Set(["CheckResonatorSpectroscopy", "CheckQubitSpectroscopy"]);

interface TaskHistoryViewerProps {
  chipId: string;
  qubitId: string;
  taskName: string;
  startAt: string;
  endAt: string;
}

interface TaskHistoryItem extends Task {
  taskId: string;
}

type OutputValue = {
  value: number | string | boolean | null;
  unit?: string;
};

function statusMeta(status: string | undefined) {
  if (status === "completed") {
    return {
      label: "Completed",
      badgeClass: "badge-success",
      iconClass: "text-success",
      Icon: CheckCircle2,
    };
  }
  if (status === "failed") {
    return {
      label: "Failed",
      badgeClass: "badge-error",
      iconClass: "text-error",
      Icon: AlertCircle,
    };
  }
  if (status === "running" || status === "scheduled") {
    return {
      label: status.charAt(0).toUpperCase() + status.slice(1),
      badgeClass: "badge-info",
      iconClass: "text-info",
      Icon: Clock3,
    };
  }
  return {
    label: status || "Unknown",
    badgeClass: "badge-ghost",
    iconClass: "text-base-content/40",
    Icon: HelpCircle,
  };
}

function normalizeOutputValue(value: unknown): OutputValue {
  if (typeof value === "object" && value !== null && "value" in value) {
    const parameter = value as { value?: unknown; unit?: unknown };
    const raw = parameter.value;
    return {
      value:
        typeof raw === "number" || typeof raw === "string" || typeof raw === "boolean"
          ? raw
          : raw == null
            ? null
            : String(raw),
      unit: typeof parameter.unit === "string" ? parameter.unit : undefined,
    };
  }
  return {
    value:
      typeof value === "number" || typeof value === "string" || typeof value === "boolean"
        ? value
        : value == null
          ? null
          : String(value),
  };
}

function formatOutputValue(value: OutputValue, precision = 6): string {
  const displayValue =
    typeof value.value === "number"
      ? Number.isInteger(value.value)
        ? String(value.value)
        : value.value.toPrecision(precision)
      : value.value == null
        ? "-"
        : String(value.value);
  return value.unit ? `${displayValue} ${value.unit}` : displayValue;
}

function outputEntries(task: TaskHistoryItem | undefined): Array<[string, string]> {
  if (!task?.output_parameters) return [];
  return Object.entries(task.output_parameters).map(([key, value]) => [
    key,
    formatOutputValue(normalizeOutputValue(value)),
  ]);
}

function firstFigurePath(task: TaskHistoryItem | undefined): string | null {
  if (!task?.figure_path || task.figure_path.length === 0) return null;
  return task.figure_path[0] ?? null;
}

function taskResultHref(task: TaskHistoryItem): string {
  return `/task-results/${task.task_id || task.taskId}`;
}

export function TaskHistoryViewer({
  chipId,
  qubitId,
  taskName,
  startAt,
  endAt,
}: TaskHistoryViewerProps) {
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);

  const { data, isLoading, error } = useGetQubitTaskHistory(
    qubitId,
    { chip_id: chipId, task: taskName },
    {
      query: {
        staleTime: 30000,
      },
    },
  );

  const taskHistory = useMemo((): TaskHistoryItem[] => {
    if (!data?.data?.data) return [];
    const startMs = new Date(startAt).getTime();
    const endMs = new Date(endAt).getTime();

    return Object.entries(data.data.data)
      .map(([taskId, task]) => ({
        taskId,
        ...task,
      }))
      .filter((task) => {
        if (!task.start_at) return false;
        const taskStartMs = new Date(task.start_at).getTime();
        return taskStartMs >= startMs && taskStartMs <= endMs;
      })
      .sort((a, b) => {
        const timeA = a.start_at ? new Date(a.start_at).getTime() : 0;
        const timeB = b.start_at ? new Date(b.start_at).getTime() : 0;
        return timeB - timeA;
      });
  }, [data, endAt, startAt]);

  useEffect(() => {
    if (taskHistory.length === 0) {
      setSelectedTaskId(null);
      return;
    }
    if (!selectedTaskId || !taskHistory.some((task) => task.taskId === selectedTaskId)) {
      setSelectedTaskId(taskHistory[0].taskId);
    }
  }, [taskHistory, selectedTaskId]);

  const selectedTask = useMemo(
    (): TaskHistoryItem | undefined => taskHistory.find((task) => task.taskId === selectedTaskId),
    [taskHistory, selectedTaskId],
  );

  const statusCounts = useMemo(() => {
    return taskHistory.reduce<Record<string, number>>((counts, task) => {
      const key = task.status || "unknown";
      counts[key] = (counts[key] ?? 0) + 1;
      return counts;
    }, {});
  }, [taskHistory]);

  const outputs = outputEntries(selectedTask);
  const figurePath = firstFigurePath(selectedTask);
  const selectedMeta = statusMeta(selectedTask?.status);
  const SelectedIcon = selectedMeta.Icon;

  if (isLoading) {
    return (
      <div className="rounded-lg border border-base-300 bg-base-100 p-8">
        <div className="flex items-center justify-center gap-3 text-sm text-base-content/60">
          <span className="loading loading-spinner loading-sm" />
          Loading task history
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="alert alert-error">
        <span>Failed to load task history: {(error as Error)?.message}</span>
      </div>
    );
  }

  if (taskHistory.length === 0) {
    return (
      <div className="rounded-lg border border-base-300 bg-base-100 p-8 text-center">
        <Clock3 className="mx-auto h-8 w-8 text-base-content/35" />
        <div className="mt-3 text-sm font-medium">No task history available</div>
        <div className="mt-1 text-xs text-base-content/55">
          This qubit has no recorded runs for {taskName} in the selected range.
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-base-300 bg-base-100 px-4 py-3">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold">{taskName}</span>
              <span className="badge badge-sm badge-outline">Q{qubitId}</span>
              <span className="badge badge-sm badge-primary">{taskHistory.length} runs</span>
            </div>
            <p className="mt-1 text-xs text-base-content/55">
              Review previous runs in the selected range. Open the full task result for figures,
              notes, and provenance.
            </p>
          </div>

          <div className="flex flex-wrap gap-1.5">
            {Object.entries(statusCounts).map(([status, count]) => {
              const meta = statusMeta(status);
              return (
                <span key={status} className={`badge badge-sm ${meta.badgeClass}`}>
                  {meta.label}: {count}
                </span>
              );
            })}
          </div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[360px_minmax(0,1fr)]">
        <div className="flex min-h-0 flex-col border-r border-base-300 pr-4">
          <div className="mb-3 shrink-0">
            <div className="mb-1 flex items-center gap-2">
              <History className="h-4 w-4 text-primary" />
              <h3 className="text-sm font-bold text-base-content">Execution History</h3>
            </div>
            <p className="text-xs text-base-content/50">
              {taskHistory.length} runs with {taskName}
            </p>
          </div>
          <div className="max-h-[calc(100vh-360px)] min-h-80 overflow-y-auto">
            <div className="flex flex-col gap-2">
              {taskHistory.map((task, index) => {
                const meta = statusMeta(task.status);
                const StatusIcon = meta.Icon;
                const isSelected = selectedTaskId === task.taskId;
                return (
                  <button
                    key={task.taskId}
                    type="button"
                    className={`w-full rounded-lg border-2 p-3 text-left transition-all ${
                      isSelected
                        ? "border-primary bg-primary text-primary-content"
                        : "border-transparent bg-base-200 hover:border-primary/30 hover:bg-base-300"
                    }`}
                    onClick={() => setSelectedTaskId(task.taskId)}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex min-w-0 items-center gap-2">
                          <StatusIcon
                            className={`h-4 w-4 shrink-0 ${isSelected ? "" : meta.iconClass}`}
                          />
                          <span className="truncate text-sm font-bold">
                            {task.start_at
                              ? formatDateTime(task.start_at, "MM/dd HH:mm")
                              : "No start time"}
                          </span>
                        </div>
                        <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs opacity-70">
                          <span className="font-mono">{task.taskId.slice(-8)}</span>
                          {task.elapsed_time && <span>{task.elapsed_time}</span>}
                        </div>
                        {task.message && (
                          <div className="mt-1 truncate text-xs opacity-70">{task.message}</div>
                        )}
                        {index === 0 && (
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
                        <span className="text-xs opacity-60">#{index + 1}</span>
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

        <div className="min-h-0 overflow-y-auto">
          {selectedTask ? (
            <div className="flex flex-col">
              <div className="mb-3 flex shrink-0 items-center justify-between">
                <div className="flex items-center gap-2">
                  <FileText className="h-4 w-4 text-accent" />
                  <h3 className="text-sm font-bold text-base-content">Task Details</h3>
                </div>
                <div className="text-xs text-base-content/60">
                  {taskHistory.findIndex((task) => task.taskId === selectedTask.taskId) + 1} /{" "}
                  {taskHistory.length}
                </div>
              </div>

              <div className="flex flex-col gap-3 border-b border-base-300 pb-3 md:flex-row md:items-start md:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <SelectedIcon className={`h-4 w-4 ${selectedMeta.iconClass}`} />
                    <span className={`badge badge-sm ${selectedMeta.badgeClass}`}>
                      {selectedMeta.label}
                    </span>
                    <span className="font-mono text-xs text-base-content/55">
                      {selectedTask.taskId}
                    </span>
                  </div>
                  <div className="mt-2 grid gap-2 text-xs text-base-content/60 sm:grid-cols-3">
                    <div>
                      <div className="font-medium text-base-content/45">Started</div>
                      <div>
                        {selectedTask.start_at
                          ? formatDateTime(selectedTask.start_at, "MM/dd HH:mm:ss")
                          : "-"}
                      </div>
                    </div>
                    <div>
                      <div className="font-medium text-base-content/45">Ended</div>
                      <div>
                        {selectedTask.end_at
                          ? formatDateTime(selectedTask.end_at, "MM/dd HH:mm:ss")
                          : "-"}
                      </div>
                    </div>
                    <div>
                      <div className="font-medium text-base-content/45">Duration</div>
                      <div>{selectedTask.elapsed_time || "-"}</div>
                    </div>
                  </div>
                </div>

                <Link className="btn btn-primary btn-sm gap-1" href={taskResultHref(selectedTask)}>
                  <ExternalLink className="h-3.5 w-3.5" />
                  Open result
                </Link>
              </div>

              <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(280px,0.9fr)]">
                <div className="min-w-0 space-y-4">
                  <div>
                    <div className="mb-2 text-xs font-medium text-base-content/55">
                      Primary figure
                    </div>
                    <div className="flex h-[280px] items-center justify-start overflow-x-auto overflow-y-hidden rounded-lg bg-base-200 p-3">
                      {figurePath ? (
                        <TaskFigure
                          path={figurePath}
                          qid={qubitId}
                          className="h-full w-auto object-contain"
                        />
                      ) : (
                        <div className="flex w-full flex-col items-center justify-center text-base-content/40">
                          <FileText className="mb-3 h-12 w-12 opacity-30" />
                          <p className="text-sm">No figure available for this task</p>
                        </div>
                      )}
                    </div>
                    {(selectedTask.figure_path?.length ?? 0) > 1 && (
                      <div className="mt-2 text-xs text-base-content/45">
                        +{(selectedTask.figure_path?.length ?? 1) - 1} more figure(s) in task result
                      </div>
                    )}
                  </div>

                  <div className="rounded-lg bg-base-200 p-3 text-xs text-base-content/60">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold">Task Name:</span>
                      <span className="font-mono">{selectedTask.name || taskName}</span>
                    </div>
                    <div className="mt-1 flex items-center gap-2">
                      <span className="font-semibold">Task ID:</span>
                      <Link
                        href={taskResultHref(selectedTask)}
                        className="link link-primary truncate font-mono"
                      >
                        {selectedTask.task_id || selectedTask.taskId}
                      </Link>
                    </div>
                    {selectedTask.message && (
                      <div className="mt-2 border-t border-base-300 pt-2 text-base-content/70">
                        {selectedTask.message}
                      </div>
                    )}
                  </div>
                </div>

                <div className="min-w-0 space-y-4">
                  <div>
                    <div className="mb-2 text-xs font-medium text-base-content/55">
                      Output parameters
                    </div>
                    {outputs.length > 0 ? (
                      <div className="divide-y divide-base-300 rounded-lg border border-base-300">
                        {outputs.slice(0, 8).map(([key, value]) => (
                          <div
                            key={key}
                            className="grid grid-cols-[minmax(0,1fr)_auto] gap-3 px-3 py-2 text-xs"
                          >
                            <span className="truncate text-base-content/60">{key}</span>
                            <span className="font-mono text-base-content">{value}</span>
                          </div>
                        ))}
                        {outputs.length > 8 && (
                          <div className="px-3 py-2 text-xs text-base-content/45">
                            +{outputs.length - 8} more in task result
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="rounded-lg border border-dashed border-base-300 p-4 text-xs text-base-content/45">
                        No output parameters
                      </div>
                    )}
                  </div>

                  {REANALYZABLE_TASKS.has(selectedTask.name ?? "") && (
                    <ReanalysisPanel
                      chipId={chipId}
                      qubitId={qubitId}
                      taskName={selectedTask.name ?? ""}
                      sourceTaskId={selectedTask.taskId}
                    />
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="flex min-h-80 flex-col items-center justify-center text-base-content/40">
              <FileText className="mb-3 h-10 w-10 opacity-30" />
              <p className="text-sm">Select a run to preview it.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
