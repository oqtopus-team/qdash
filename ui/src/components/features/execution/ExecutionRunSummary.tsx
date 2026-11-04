"use client";

import { LoaderCircle } from "lucide-react";

import { QubitTile } from "@/components/ui/QubitTile";
import { isExecutionInProgress, isExecutionTerminal } from "@/lib/executionStatus";

interface SummaryTask {
  name?: string | null;
  qid?: string | null;
  status?: string | null;
}

interface ExecutionRunSummaryProps {
  status?: string | null;
  tasks: SummaryTask[];
  className?: string;
}

/**
 * One line that says how far an in-flight execution has got: how many tasks have finished and
 * which one is being measured now, or that the run is waiting to start or being cancelled. There
 * is no total and no bar on purpose: a flow registers tasks as it goes, so a denominator would
 * shrink the apparent progress each time new tasks appear. Renders nothing once the execution has
 * finished, since the task list then tells the story.
 */
export function ExecutionRunSummary({ status, tasks, className = "" }: ExecutionRunSummaryProps) {
  if (!isExecutionInProgress(status)) return null;

  const done = tasks.filter((task) => isExecutionTerminal(task.status)).length;
  const current = tasks.find((task) => task.status === "running");

  let headline: string;
  if (status === "cancelling") headline = "Cancelling";
  else if (status === "running") headline = "Running";
  else headline = "Waiting to start";

  return (
    <div
      className={`flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg bg-base-200/60 p-3 text-sm ${className}`}
      role="status"
    >
      <LoaderCircle
        className="h-4 w-4 shrink-0 animate-spin text-primary motion-reduce:animate-none"
        aria-hidden="true"
      />
      <span className="font-medium">{headline}</span>
      {done > 0 && (
        <span className="text-base-content/60">
          · {done} task{done === 1 ? "" : "s"} done
        </span>
      )}
      {current && status === "running" && (
        <span className="flex items-center gap-1.5 text-base-content/60">
          · now {current.name || "a task"}
          {current.qid && <QubitTile qid={current.qid} />}
        </span>
      )}
    </div>
  );
}
