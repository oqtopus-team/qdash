"use client";

import { useMemo } from "react";
import { CheckCircle2, Circle, ExternalLink, Loader2, MinusCircle, XCircle } from "lucide-react";
import { useGetExecution } from "@/client/execution/execution";
import { FigureStrip } from "@/components/features/chat/ChatFigures";
import type { PipelineProgress, Task } from "@/schemas";

const POLL_MS = 5000;
const RECENT_TASKS = 6;

/** Execution ids pi-qdash's wait tool takes; `executionId` is its argument name. */
export function executionIdFromArgs(args: unknown): string | null {
  if (!args || typeof args !== "object") return null;
  const value =
    (args as { executionId?: unknown; execution_id?: unknown }).executionId ??
    (args as { execution_id?: unknown }).execution_id;
  return typeof value === "string" && value.trim() ? value : null;
}

/** Tasks that have reached a terminal state, most recent last. */
export function finishedTasks(tasks: Task[]): Task[] {
  return tasks.filter((t) => t.status === "completed" || t.status === "failed");
}

function taskLabel(task: Task): string {
  return task.qid ? `${task.name ?? "task"} · ${task.qid}` : (task.name ?? "task");
}

/**
 * What an execution is doing right now, for the chat to show while the
 * assistant waits on it: progress, the latest finished tasks, and their
 * figures as they appear. Polls while the execution runs and stops once it
 * reaches a terminal state.
 */
export function ExecutionProgress({ executionId }: { executionId: string }) {
  const query = useGetExecution(executionId, {
    query: {
      refetchInterval: (q) => {
        const detail = q.state.data?.data;
        const status = detail?.pipeline?.status ?? detail?.status;
        return status === "running" || status === "scheduled" || status === undefined
          ? POLL_MS
          : false;
      },
      staleTime: 0,
    },
  });
  const execution = query.data?.data;
  const tasks = useMemo(() => execution?.task ?? [], [execution?.task]);
  const finished = useMemo(() => finishedTasks(tasks), [tasks]);
  // A task can carry several figures; show them all, in task order.
  const figures = useMemo(
    () =>
      finished.flatMap((t) =>
        (Array.isArray(t.figure_path) ? t.figure_path : []).filter(
          (p): p is string => typeof p === "string" && p.length > 0,
        ),
      ),
    [finished],
  );

  if (!execution) {
    return (
      <div className="chat-execution-progress text-xs text-base-content/50">
        <Loader2 className="w-3 h-3 animate-spin" />
        Loading execution {executionId}…
      </div>
    );
  }

  if (execution.pipeline) {
    return <PipelineCard pipeline={execution.pipeline} chipId={execution.chip_id} />;
  }

  const failed = finished.filter((t) => t.status === "failed").length;
  const running = execution.status === "running" || execution.status === "scheduled";
  const href = execution.chip_id
    ? `/execution/${encodeURIComponent(execution.chip_id)}/${encodeURIComponent(executionId)}`
    : null;

  return (
    <div className="chat-execution-progress" data-testid="execution-progress">
      <div className="flex items-center gap-2 text-xs">
        {running ? (
          <Loader2 className="w-3 h-3 animate-spin text-primary" />
        ) : execution.status === "completed" ? (
          <CheckCircle2 className="w-3 h-3 text-success" />
        ) : (
          <XCircle className="w-3 h-3 text-error" />
        )}
        <span className="font-medium">{execution.name || executionId}</span>
        <span className="text-base-content/50">
          · {execution.status} · {finished.length}/{tasks.length} tasks
          {failed > 0 ? ` · ${failed} failed` : ""}
        </span>
        {href && (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="ml-auto inline-flex items-center gap-1 text-base-content/50 hover:text-base-content"
            aria-label="Open execution"
          >
            <ExternalLink className="w-3 h-3" />
          </a>
        )}
      </div>

      {finished.length > 0 && (
        <ul className="mt-1.5 space-y-0.5 text-[11px]">
          {finished.slice(-RECENT_TASKS).map((task) => (
            <li key={task.task_id ?? taskLabel(task)} className="flex items-center gap-1.5">
              {task.status === "failed" ? (
                <XCircle className="w-3 h-3 shrink-0 text-error" />
              ) : (
                <CheckCircle2 className="w-3 h-3 shrink-0 text-success" />
              )}
              <span className="truncate text-base-content/70">{taskLabel(task)}</span>
            </li>
          ))}
          {finished.length > RECENT_TASKS && (
            <li className="text-base-content/40">+{finished.length - RECENT_TASKS} earlier</li>
          )}
        </ul>
      )}

      {figures.length > 0 && <FigureStrip paths={figures} compact className="mt-2" />}
    </div>
  );
}

function StepIcon({ status }: { status: string }) {
  switch (status) {
    case "running":
    case "scheduled":
      return <Loader2 className="w-3 h-3 shrink-0 animate-spin text-primary" />;
    case "completed":
      return <CheckCircle2 className="w-3 h-3 shrink-0 text-success" />;
    case "failed":
    case "cancelled":
      return <XCircle className="w-3 h-3 shrink-0 text-error" />;
    case "skipped":
      return <MinusCircle className="w-3 h-3 shrink-0 text-base-content/30" />;
    default:
      return <Circle className="w-3 h-3 shrink-0 text-base-content/30" />;
  }
}

/**
 * A pipeline run: every planned step with its own progress, and the figures
 * of all finished tasks so far. Steps that only filter are listed but do not
 * run hardware.
 */
function PipelineCard({ pipeline, chipId }: { pipeline: PipelineProgress; chipId?: string }) {
  const running = pipeline.status === "running";
  const figures = pipeline.steps.flatMap((step) => step.figure_paths ?? []);
  const href = chipId
    ? `/execution/${encodeURIComponent(chipId)}/${encodeURIComponent(pipeline.root_execution_id)}`
    : null;
  const finishedSteps = pipeline.steps.filter(
    (s) => s.kind !== "transform" && (s.status === "completed" || s.status === "failed"),
  ).length;
  const totalSteps = pipeline.steps.filter((s) => s.kind !== "transform").length;

  return (
    <div className="chat-execution-progress" data-testid="execution-progress">
      <div className="flex items-center gap-2 text-xs">
        <StepIcon status={pipeline.status} />
        <span className="font-medium">{pipeline.name}</span>
        <span className="text-base-content/50">
          · {pipeline.status} · {finishedSteps}/{totalSteps} steps
        </span>
        {href && (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="ml-auto inline-flex items-center gap-1 text-base-content/50 hover:text-base-content"
            aria-label="Open execution"
          >
            <ExternalLink className="w-3 h-3" />
          </a>
        )}
      </div>

      <ol className="mt-1.5 space-y-0.5 text-[11px]">
        {pipeline.steps.map((step) => (
          <li key={step.index} className="flex items-center gap-1.5">
            <StepIcon status={step.status} />
            <span
              className={`truncate ${
                step.status === "pending" || step.status === "skipped"
                  ? "text-base-content/40"
                  : "text-base-content/70"
              }`}
            >
              {step.index}. {step.name}
            </span>
            {step.kind !== "transform" && step.execution_id && (
              <span className="ml-auto shrink-0 tabular-nums text-base-content/40">
                {step.task_finished ?? 0}/{step.task_total ?? 0}
                {step.task_failed ? ` · ${step.task_failed} failed` : ""}
              </span>
            )}
          </li>
        ))}
      </ol>

      {figures.length > 0 && <FigureStrip paths={figures} compact className="mt-2" />}
      {running && finishedSteps === 0 && figures.length === 0 && (
        <div className="mt-1.5 text-[11px] text-base-content/40">
          Waiting for the first results…
        </div>
      )}
    </div>
  );
}
