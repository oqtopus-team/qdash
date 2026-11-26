"use client";

import { Ban, CircleAlert, CircleCheck, CircleDashed, CircleX, LoaderCircle } from "lucide-react";
import type { SubagentStatus, SubagentTask } from "@/types/agentChat";
import { ChatMarkdown } from "@/components/features/chat/ChatMarkdown";

/**
 * The research tasks a `delegate_research` call handed to read-only
 * subagents: one row per task with its title, its state in words, its
 * progress, and on request its answer or why it gave none. Shown while the
 * call runs and, from the saved trace, after a reload.
 */

/** The tool that delegates research to subagents (agent-runtime subagent-tool.ts). */
export const SUBAGENT_TOOL = "delegate_research";

const STATUS: Record<SubagentStatus, { label: string; badge: string }> = {
  queued: { label: "Queued", badge: "badge-ghost" },
  running: { label: "Running", badge: "badge-info" },
  done: { label: "Done", badge: "badge-success" },
  error: { label: "Failed", badge: "badge-error" },
  cancelled: { label: "Stopped", badge: "badge-ghost" },
  interrupted: { label: "Interrupted", badge: "badge-warning" },
};

function StatusIcon({ status }: { status: SubagentStatus }) {
  const className = "mt-0.5 h-3.5 w-3.5 shrink-0";
  switch (status) {
    case "running":
      return (
        <LoaderCircle
          className={`${className} text-info motion-safe:animate-spin`}
          aria-hidden="true"
        />
      );
    case "done":
      return <CircleCheck className={`${className} text-success`} aria-hidden="true" />;
    case "error":
      return <CircleX className={`${className} text-error`} aria-hidden="true" />;
    case "interrupted":
      return <CircleAlert className={`${className} text-warning`} aria-hidden="true" />;
    case "cancelled":
      return <Ban className={`${className} text-base-content/40`} aria-hidden="true" />;
    default:
      return <CircleDashed className={`${className} text-base-content/40`} aria-hidden="true" />;
  }
}

function seconds(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
}

/** Tool calls, time, and while running what the subagent is doing. */
function progressLine(task: SubagentTask, now: number): string {
  const parts = [`${task.toolCalls} tool call${task.toolCalls === 1 ? "" : "s"}`];
  if (task.startedAt !== undefined) {
    const end = task.endedAt ?? (task.status === "running" ? now : undefined);
    if (end !== undefined) parts.push(seconds(end - task.startedAt));
  }
  if (task.status === "running" && task.activity) {
    parts.push(task.activity === "thinking" ? "thinking" : task.activity);
  }
  return parts.join(" · ");
}

function SubagentRow({ task, now }: { task: SubagentTask; now: number }) {
  const status = STATUS[task.status];
  const detail = task.result ?? task.error;
  return (
    <li
      className="list-row items-start gap-2 px-3 py-2"
      data-testid="subagent-task"
      data-status={task.status}
    >
      <StatusIcon status={task.status} />
      <div className="min-w-0">
        <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5">
          <span className="min-w-0 truncate text-sm text-base-content/80" title={task.title}>
            {task.title}
          </span>
          <span className={`badge badge-soft badge-xs ${status.badge}`}>{status.label}</span>
        </div>
        {task.status !== "queued" && (
          <p className="mt-0.5 truncate text-xs tabular-nums text-base-content/50">
            {progressLine(task, now)}
          </p>
        )}
        {detail && (
          <details className="group mt-1 text-xs">
            <summary className="cursor-pointer select-none text-base-content/55 hover:text-base-content/80">
              {task.result ? "Findings" : "Error"}
            </summary>
            {task.result ? (
              <div className="mt-1 max-h-72 overflow-y-auto text-sm text-base-content/80">
                <ChatMarkdown>{task.result}</ChatMarkdown>
              </div>
            ) : (
              <p className="mt-1 whitespace-pre-wrap break-words font-mono text-error">
                {task.error}
              </p>
            )}
          </details>
        )}
      </div>
    </li>
  );
}

export function SubagentTasks({ tasks, now }: { tasks: SubagentTask[]; now: number }) {
  const done = tasks.filter((t) => t.status === "done").length;
  return (
    <ul
      className="list mt-1.5 rounded-box border border-base-300 bg-base-100"
      aria-label={`Research subagents: ${done} of ${tasks.length} done`}
      data-testid="subagent-tasks"
    >
      {tasks.map((task) => (
        <SubagentRow key={task.id} task={task} now={now} />
      ))}
    </ul>
  );
}
