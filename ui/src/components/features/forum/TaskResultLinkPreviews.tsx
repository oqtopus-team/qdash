"use client";

import Link from "next/link";
import { Activity, ArrowUpRight, Clock } from "lucide-react";

import { useGetTaskResult } from "@/client/task/task";
import { TaskFigure } from "@/components/charts/TaskFigure";
import { formatRelativeTime } from "@/lib/utils/datetime";

function statusClass(status: string): string {
  if (status === "success") return "badge-success";
  if (status === "failed") return "badge-error";
  if (status === "running") return "badge-warning";
  return "badge-ghost";
}

function TaskResultLinkPreview({ taskId }: { taskId: string }) {
  const { data, isLoading, isError } = useGetTaskResult(taskId, {
    query: { staleTime: 30_000, retry: false },
  });
  const taskResult = data?.data;

  if (isError) return null;

  if (isLoading || !taskResult) {
    return (
      <div className="flex min-h-20 items-center gap-3 rounded-lg border border-base-300 bg-base-100 px-4 py-3">
        <span className="loading loading-spinner loading-sm text-primary" />
        <span className="text-xs text-base-content/50">Loading task result…</span>
      </div>
    );
  }

  const figurePath = taskResult.figure_path[0];
  const jsonFigurePath = taskResult.json_figure_path[0];

  return (
    <Link
      href={`/task-results/${encodeURIComponent(taskId)}`}
      className="group grid overflow-hidden rounded-lg border border-base-300 bg-base-100 transition-colors hover:border-primary/50 sm:grid-cols-[minmax(0,1fr)_12rem]"
    >
      <div className="min-w-0 p-3">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
          <span className="truncate text-sm font-semibold">{taskResult.task_name}</span>
          <span className={`badge badge-sm ${statusClass(taskResult.status)}`}>
            {taskResult.status}
          </span>
          <ArrowUpRight
            className="ml-auto h-4 w-4 shrink-0 text-base-content/35 transition-colors group-hover:text-primary"
            aria-hidden="true"
          />
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-base-content/55">
          <span className="badge badge-sm badge-neutral">Q{taskResult.qid}</span>
          {taskResult.chip_id && <span>{taskResult.chip_id}</span>}
          {taskResult.end_at && (
            <span className="inline-flex items-center gap-1">
              <Clock className="h-3 w-3" aria-hidden="true" />
              {formatRelativeTime(taskResult.end_at)}
            </span>
          )}
        </div>
        <div className="mt-2 truncate font-mono text-[11px] text-base-content/40">{taskId}</div>
      </div>
      {(figurePath || jsonFigurePath) && (
        <div className="hidden h-28 items-center justify-center overflow-hidden border-l border-base-300 bg-base-200/40 p-2 sm:flex">
          <TaskFigure
            path={figurePath ?? jsonFigurePath}
            jsonFigurePath={jsonFigurePath}
            qid={taskResult.qid}
            className="max-h-full max-w-full object-contain"
            hideExpandButton
          />
        </div>
      )}
    </Link>
  );
}

export function TaskResultLinkPreviews({ taskIds }: { taskIds: string[] }) {
  if (taskIds.length === 0) return null;

  return (
    <div className="mt-4 space-y-2">
      <div className="text-xs font-semibold uppercase tracking-wide text-base-content/45">
        Linked task results
      </div>
      {taskIds.map((taskId) => (
        <TaskResultLinkPreview key={taskId} taskId={taskId} />
      ))}
    </div>
  );
}
