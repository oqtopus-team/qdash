"use client";

import Link from "next/link";

import { AlertCircle, CheckCircle2, Clock3, ExternalLink, HelpCircle, Loader2 } from "lucide-react";

import type { TaskInfo, TaskResultResponse } from "@/schemas";

import { useGetTaskResult } from "@/client/task/task";
import { useListTaskResults } from "@/client/task-result/task-result";
import { TaskFigure } from "@/components/charts/TaskFigure";
import { formatDateTime } from "@/lib/utils/datetime";

interface QubitTaskCardProps {
  task: TaskInfo;
  chipId: string;
  qubitId: string;
  startAt: string;
  endAt: string;
  onViewDetails: (taskName: string) => void;
}

type OutputValue = {
  value: number | string | boolean | null;
  unit?: string;
};

function formatTaskName(name: string): string {
  return name
    .replace(/^Check/, "")
    .replace(/_/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .trim();
}

function firstFigurePath(taskData: TaskResultResponse): string | null {
  if (!taskData.figure_path || taskData.figure_path.length === 0) return null;
  return taskData.figure_path[0] ?? null;
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

function formatOutputValue(value: OutputValue): string {
  const displayValue =
    typeof value.value === "number"
      ? Number.isInteger(value.value)
        ? String(value.value)
        : value.value.toPrecision(4)
      : value.value == null
        ? "-"
        : String(value.value);
  return value.unit ? `${displayValue} ${value.unit}` : displayValue;
}

function outputPreview(taskData: TaskResultResponse): Array<[string, string]> {
  return Object.entries(taskData.output_parameters ?? {})
    .slice(0, 3)
    .map(([key, value]) => [key, formatOutputValue(normalizeOutputValue(value))]);
}

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
      Icon: Loader2,
    };
  }
  return {
    label: "No data",
    badgeClass: "badge-ghost",
    iconClass: "text-base-content/40",
    Icon: HelpCircle,
  };
}

export function QubitTaskCard({
  task,
  chipId,
  qubitId,
  startAt,
  endAt,
  onViewDetails,
}: QubitTaskCardProps) {
  const { data: listData, isLoading: isListLoading } = useListTaskResults(
    {
      chip_id: chipId,
      task_name: task.name,
      qid: qubitId,
      start_from: startAt,
      start_to: endAt,
      limit: 1,
    },
    { query: { enabled: !!chipId && !!task.name && !!qubitId, staleTime: 30_000 } },
  );
  const taskResultId = listData?.data.items[0]?.task_id ?? null;
  const { data: taskResultData, isLoading: isDetailLoading } = useGetTaskResult(
    taskResultId ?? "",
    {
      query: { enabled: !!taskResultId, staleTime: 30_000 },
    },
  );

  const taskData: TaskResultResponse | null = taskResultData?.data ?? null;
  const isLoading = isListLoading || (!!taskResultId && isDetailLoading);
  const figurePath = taskData ? firstFigurePath(taskData) : null;
  const outputs = taskData ? outputPreview(taskData) : [];
  const remainingOutputCount = taskData?.output_parameters
    ? Math.max(0, Object.keys(taskData.output_parameters).length - outputs.length)
    : 0;
  const meta = statusMeta(taskData?.status);
  const StatusIcon = meta.Icon;
  const taskResultHref = taskData?.task_id ? `/task-results/${taskData.task_id}` : null;

  if (isLoading) {
    return (
      <div className="rounded-lg border border-base-300 bg-base-100 p-4">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="skeleton h-5 w-40" />
            <div className="skeleton mt-2 h-3 w-28" />
          </div>
          <span className="loading loading-spinner loading-sm" />
        </div>
      </div>
    );
  }

  return (
    <article className="group rounded-lg border border-base-300 bg-base-100 transition-colors hover:border-primary/40">
      <div className="grid gap-3 p-3 sm:grid-cols-[84px_minmax(0,1fr)_auto] sm:items-center sm:p-3">
        <div className="relative hidden h-16 overflow-hidden rounded-md border border-base-300 bg-base-200 sm:block">
          {figurePath ? (
            <TaskFigure path={figurePath} qid={qubitId} className="h-full w-full object-contain" />
          ) : (
            <div className="flex h-full items-center justify-center text-base-content/35">
              <StatusIcon className={`h-5 w-5 ${meta.iconClass}`} />
            </div>
          )}
        </div>

        <div className="min-w-0 space-y-1.5">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <StatusIcon className={`h-4 w-4 shrink-0 ${meta.iconClass}`} />
            <h3 className="min-w-0 truncate text-sm font-semibold text-base-content">
              {formatTaskName(task.name)}
            </h3>
            <span className={`badge badge-xs ${meta.badgeClass}`}>{meta.label}</span>
            {task.category && <span className="badge badge-xs badge-outline">{task.category}</span>}
          </div>

          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-base-content/55">
            <span className="font-mono text-base-content/45">{task.name}</span>
            {taskData?.start_at && (
              <span className="inline-flex items-center gap-1">
                <Clock3 className="h-3 w-3" />
                {formatDateTime(taskData.start_at, "MM/dd HH:mm")}
              </span>
            )}
            {taskData?.elapsed_time && <span>{taskData.elapsed_time}</span>}
          </div>

          {outputs.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {outputs.map(([key, value]) => (
                <span
                  key={key}
                  className="inline-flex max-w-full items-center gap-1 rounded border border-base-300 bg-base-200/70 px-2 py-1 text-xs"
                >
                  <span className="truncate text-base-content/55">{key}</span>
                  <span className="font-mono text-base-content">{value}</span>
                </span>
              ))}
              {remainingOutputCount > 0 && (
                <span className="rounded border border-base-300 px-2 py-1 text-xs text-base-content/55">
                  +{remainingOutputCount} more
                </span>
              )}
            </div>
          ) : (
            <div className="text-xs text-base-content/45">
              {taskData ? "No output parameters" : "No execution result for this selection"}
            </div>
          )}
        </div>

        <div className="flex justify-end sm:self-stretch">
          {taskResultHref ? (
            <Link className="btn btn-ghost btn-sm gap-1 sm:self-center" href={taskResultHref}>
              <ExternalLink className="h-3.5 w-3.5" />
              Result
            </Link>
          ) : (
            <button
              className="btn btn-ghost btn-sm gap-1 sm:self-center"
              onClick={() => onViewDetails(task.name)}
            >
              <ExternalLink className="h-3.5 w-3.5" />
              History
            </button>
          )}
        </div>
      </div>
    </article>
  );
}
