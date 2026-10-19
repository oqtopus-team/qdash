"use client";

import { useListEvaluationRuns } from "@/client/evaluation/evaluation";
import { formatDateTime } from "@/lib/utils/datetime";
import type { EvaluationRunSummary } from "@/schemas";

import { modeLabel, triggerLabel } from "./evaluationDisplay";

interface RunPickerProps {
  /** Candidates: runs of this chip and task, newest first. */
  chipId: string;
  taskName: string;
  /** The run already chosen, left out of the candidates. */
  excludeRunId?: string;
  onPick: (runId: string) => void;
  label?: string;
  className?: string;
}

/** One line per run: when, how, and what it reports. */
function runOptionLabel(run: EvaluationRunSummary): string {
  const parts = [
    formatDateTime(run.requested_at),
    triggerLabel(run.trigger),
    modeLabel(run.mode),
    run.with_examples ? "examples" : null,
    run.date ? run.date : null,
    `${run.success_count}/${run.completed_count} success`,
  ];
  return parts.filter(Boolean).join(" · ");
}

/** A select of the other runs of the same chip and task, to compare against. */
export function RunPicker({
  chipId,
  taskName,
  excludeRunId,
  onPick,
  label = "Compare with…",
  className = "",
}: RunPickerProps) {
  const { data: response, isLoading } = useListEvaluationRuns(
    { chip_id: chipId, task: taskName, limit: 50 },
    { query: { enabled: !!chipId && !!taskName } },
  );
  const candidates = (response?.data.runs ?? []).filter((run) => run.run_id !== excludeRunId);

  return (
    <select
      className={`select select-bordered select-sm ${className}`}
      value=""
      onChange={(event) => {
        if (event.target.value) onPick(event.target.value);
      }}
      disabled={isLoading || candidates.length === 0}
      aria-label={label}
      data-testid="run-picker"
    >
      <option value="">
        {isLoading
          ? "Loading runs…"
          : candidates.length === 0
            ? "No other run of this task"
            : label}
      </option>
      {candidates.map((run) => (
        <option key={run.run_id} value={run.run_id}>
          {runOptionLabel(run)}
        </option>
      ))}
    </select>
  );
}
