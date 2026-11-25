"use client";

import { useMemo } from "react";
import {
  Ban,
  CheckCircle2,
  Circle,
  ExternalLink,
  Loader2,
  MinusCircle,
  XCircle,
} from "lucide-react";
import { useGetExecution } from "@/client/execution/execution";
import { FigureStrip } from "@/components/features/chat/ChatFigures";
import { ChatLink } from "@/components/features/chat/ChatPreviewLink";
import { chatLinkPagePath } from "@/lib/chatLinks";
import { isTransformExecution, transformRecordOf, transformSummary } from "@/lib/transformStep";
import type { PipelineProgress, PipelineStepProgress, Task } from "@/schemas";

const POLL_MS = 5000;
const RECENT_TASKS = 6;
const ACTIVE_TASKS = 3;

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

/** Whether an execution, step, or task status means work is still under way. */
function isActive(status: string | undefined): boolean {
  return status === "running" || status === "scheduled";
}

/**
 * The execution page, under its chip when known; otherwise `/executions/{id}`,
 * which looks the chip up and redirects.
 */
export function executionPagePath(executionId: string, chipId?: string | null): string {
  return chatLinkPagePath({ kind: "execution", executionId, chipId: chipId || null, href: "" })!;
}

function taskResultPath(taskId: string): string {
  return chatLinkPagePath({ kind: "task-result", taskId, href: "" })!;
}

function taskLabel(task: Task): string {
  return task.qid ? `${task.name ?? "task"} · ${task.qid}` : (task.name ?? "task");
}

/** One icon per status; the status is always also given in words next to it. */
function StatusIcon({ status }: { status: string | undefined }) {
  const common = "w-3 h-3 shrink-0";
  switch (status) {
    case "running":
    case "scheduled":
      return <Loader2 className={`${common} animate-spin text-primary`} aria-hidden="true" />;
    case "completed":
      return <CheckCircle2 className={`${common} text-success`} aria-hidden="true" />;
    case "failed":
      return <XCircle className={`${common} text-error`} aria-hidden="true" />;
    case "cancelled":
      return <Ban className={`${common} text-base-content/50`} aria-hidden="true" />;
    case "skipped":
    case "not_recorded":
      return <MinusCircle className={`${common} text-base-content/30`} aria-hidden="true" />;
    default:
      return <Circle className={`${common} text-base-content/30`} aria-hidden="true" />;
  }
}

/** The full execution page, in a new tab so the conversation stays open. */
function OpenExecutionLink({ href }: { href: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="link link-hover ml-auto inline-flex shrink-0 items-center gap-1 text-base-content/60 hover:text-base-content"
    >
      Open execution
      <ExternalLink className="w-3 h-3" aria-hidden="true" />
    </a>
  );
}

/**
 * A task of the execution. A finished task links to its result, which opens
 * as a preview over the chat (figures and parameters) when one is available.
 */
function TaskRow({ task }: { task: Task }) {
  const label = taskLabel(task);
  const failed = task.status === "failed";
  const active = isActive(task.status);
  const finished = failed || task.status === "completed";
  return (
    <li className="flex min-w-0 items-center gap-1.5">
      <StatusIcon status={task.status} />
      {finished && task.task_id ? (
        <ChatLink
          href={taskResultPath(task.task_id)}
          className="link link-hover min-w-0 truncate text-base-content/70 hover:text-base-content"
        >
          {label}
        </ChatLink>
      ) : (
        <span className="min-w-0 truncate text-base-content/70">{label}</span>
      )}
      <span
        className={`ml-auto shrink-0 ${
          failed ? "text-error" : active ? "text-base-content/50" : "sr-only"
        }`}
      >
        {task.status}
      </span>
    </li>
  );
}

/**
 * What an execution is doing right now, for the chat to show while the
 * assistant waits on it: progress, the tasks running now, the latest finished
 * tasks with links to their results, and their figures as they appear. Polls
 * while the execution runs and stops once it reaches a terminal state.
 */
export function ExecutionProgress({ executionId }: { executionId: string }) {
  const query = useGetExecution(executionId, {
    query: {
      refetchInterval: (q) => {
        const detail = q.state.data?.data;
        const status = detail?.pipeline?.status ?? detail?.status;
        return isActive(status) || status === undefined ? POLL_MS : false;
      },
      staleTime: 0,
    },
  });
  const execution = query.data?.data;
  const tasks = useMemo(() => execution?.task ?? [], [execution?.task]);
  const finished = useMemo(() => finishedTasks(tasks), [tasks]);
  const active = useMemo(() => tasks.filter((t) => isActive(t.status)), [tasks]);
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
    if (query.isError) {
      return (
        <div
          className="chat-execution-progress flex flex-wrap items-center gap-x-2 gap-y-1 text-xs"
          data-testid="execution-progress-error"
        >
          <XCircle className="w-3 h-3 shrink-0 text-error" aria-hidden="true" />
          <span className="text-error">Could not load execution {executionId}.</span>
          <OpenExecutionLink href={executionPagePath(executionId)} />
        </div>
      );
    }
    return (
      <div
        role="status"
        className="chat-execution-progress flex items-center gap-2 text-xs text-base-content/50"
      >
        <Loader2 className="w-3 h-3 shrink-0 animate-spin" aria-hidden="true" />
        Loading execution {executionId}…
      </div>
    );
  }

  if (execution.pipeline) {
    return <PipelineCard pipeline={execution.pipeline} chipId={execution.chip_id} />;
  }

  if (isTransformExecution(execution.note)) {
    // A filter or schedule step: its recorded decision is the result, there are no tasks.
    const record = transformRecordOf(execution.note);
    return (
      <div className="chat-execution-progress" data-testid="execution-progress">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
          <StatusIcon status={execution.status} />
          <span className="min-w-0 truncate font-medium">{execution.name || executionId}</span>
          <span className="text-base-content/50">
            · {execution.status}
            {record ? ` · ${transformSummary(record)}` : ""}
          </span>
          <OpenExecutionLink href={executionPagePath(executionId, execution.chip_id)} />
        </div>
      </div>
    );
  }

  const failed = finished.filter((t) => t.status === "failed").length;
  const running = isActive(execution.status);
  const earlier = finished.slice(0, Math.max(0, finished.length - RECENT_TASKS));
  const recent = finished.slice(-RECENT_TASKS);
  const shownActive = active.slice(0, ACTIVE_TASKS);

  return (
    <div className="chat-execution-progress" data-testid="execution-progress">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
        <StatusIcon status={execution.status} />
        <span className="min-w-0 truncate font-medium">{execution.name || executionId}</span>
        <span className="text-base-content/50">
          · {execution.status} · {finished.length}/{tasks.length} tasks
          {failed > 0 ? ` · ${failed} failed` : ""}
        </span>
        <OpenExecutionLink href={executionPagePath(executionId, execution.chip_id)} />
      </div>

      {(finished.length > 0 || shownActive.length > 0) && (
        <ul className="mt-1.5 space-y-0.5 text-xs" aria-label="Tasks">
          {earlier.length > 0 && (
            <li>
              <details>
                <summary className="cursor-pointer select-none text-base-content/50 hover:text-base-content/80">
                  {earlier.length} earlier finished
                </summary>
                <ul className="mt-0.5 space-y-0.5">
                  {earlier.map((task, i) => (
                    <TaskRow key={task.task_id ?? `earlier-${i}`} task={task} />
                  ))}
                </ul>
              </details>
            </li>
          )}
          {recent.map((task, i) => (
            <TaskRow key={task.task_id ?? `recent-${i}`} task={task} />
          ))}
          {shownActive.map((task, i) => (
            <TaskRow key={task.task_id ?? `active-${i}`} task={task} />
          ))}
          {active.length > ACTIVE_TASKS && (
            <li className="text-base-content/50">+{active.length - ACTIVE_TASKS} more running</li>
          )}
        </ul>
      )}

      {tasks.length === 0 && (
        <p className="mt-1.5 text-xs text-base-content/50">
          {running ? "Waiting for the first task…" : "No tasks were recorded."}
        </p>
      )}

      {figures.length > 0 && <FigureStrip paths={figures} compact className="mt-2" />}
    </div>
  );
}

/** A planned step without an execution: not reached yet, never reached, or not recorded. */
function isUnstarted(status: string): boolean {
  return status === "pending" || status === "skipped" || status === "not_recorded";
}

function StepName({ step, chipId }: { step: PipelineStepProgress; chipId?: string }) {
  const label = `${step.index}. ${step.name}`;
  const muted = isUnstarted(step.status);
  if (step.execution_id) {
    // A step's own execution also reports the whole pipeline, so it opens as
    // a page (with that step's tasks) rather than as the same card again.
    return (
      <a
        href={executionPagePath(step.execution_id, chipId)}
        target="_blank"
        rel="noopener noreferrer"
        className="link link-hover min-w-0 truncate text-base-content/70 hover:text-base-content"
      >
        {label}
      </a>
    );
  }
  return (
    <span className={`min-w-0 truncate ${muted ? "text-base-content/40" : "text-base-content/70"}`}>
      {label}
    </span>
  );
}

/** What a step reports on the right: task counts, a transform's decision, or why it has none. */
function StepDetail({ step }: { step: PipelineStepProgress }) {
  if (step.status === "not_recorded") {
    return <span className="ml-auto shrink-0 text-base-content/40">not recorded</span>;
  }
  if (step.status === "skipped") {
    return <span className="ml-auto shrink-0 text-base-content/40">not reached</span>;
  }
  if (!step.execution_id) return null;
  if (step.kind === "transform") {
    // No tasks run in a transform step; its recorded decision is its result.
    const record = step.transform ?? null;
    return record ? (
      <span className="ml-auto min-w-0 truncate text-base-content/50">
        {transformSummary(record)}
      </span>
    ) : null;
  }
  return (
    <span className="ml-auto shrink-0 tabular-nums text-base-content/50">
      {step.task_finished ?? 0}/{step.task_total ?? 0}
      {step.task_failed ? <span className="text-error"> · {step.task_failed} failed</span> : null}
    </span>
  );
}

/**
 * A pipeline run: every planned step with its own progress and a link to its
 * execution once it has one, and the figures of all finished tasks so far.
 * Every step the run reaches has an execution; filters and schedules run no
 * hardware and show what they decided instead of task counts.
 */
function PipelineCard({ pipeline, chipId }: { pipeline: PipelineProgress; chipId?: string }) {
  const running = isActive(pipeline.status);
  const figures = pipeline.steps.flatMap((step) => step.figure_paths ?? []);
  // Transforms of runs recorded before they had executions are listed but not counted.
  const countedSteps = pipeline.steps.filter((s) => s.status !== "not_recorded");
  const finishedSteps = countedSteps.filter(
    (s) => s.status === "completed" || s.status === "failed",
  ).length;
  const failedTasks = countedSteps.reduce((sum, s) => sum + (s.task_failed ?? 0), 0);

  return (
    <div className="chat-execution-progress" data-testid="execution-progress">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
        <StatusIcon status={pipeline.status} />
        <span className="min-w-0 truncate font-medium">{pipeline.name}</span>
        <span className="text-base-content/50">
          · {pipeline.status} · {finishedSteps}/{countedSteps.length} steps
          {failedTasks > 0 ? ` · ${failedTasks} failed tasks` : ""}
        </span>
        <OpenExecutionLink href={executionPagePath(pipeline.root_execution_id, chipId)} />
      </div>

      <ol className="mt-1.5 space-y-0.5 text-xs" aria-label="Pipeline steps">
        {pipeline.steps.map((step) => (
          <li key={step.key || step.index} className="flex min-w-0 items-center gap-1.5">
            <StatusIcon status={step.status} />
            <StepName step={step} chipId={chipId} />
            <span className="sr-only">{step.status}</span>
            <StepDetail step={step} />
          </li>
        ))}
      </ol>

      {figures.length > 0 && <FigureStrip paths={figures} compact className="mt-2" />}
      {running && finishedSteps === 0 && figures.length === 0 && (
        <p className="mt-1.5 text-xs text-base-content/50">Waiting for the first results…</p>
      )}
    </div>
  );
}
