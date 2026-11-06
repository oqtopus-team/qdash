"use client";

import { ArrowLeftRight, ChevronRight, XCircle } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { useListEvaluationRuns } from "@/client/evaluation/evaluation";
import { useGetTaskFileSettings, useListTaskInfo } from "@/client/task-file/task-file";
import { ChipSelector } from "@/components/selectors/ChipSelector";
import { TaskSelector } from "@/components/selectors/TaskSelector";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageFiltersBar } from "@/components/ui/PageFiltersBar";
import { PageHeader } from "@/components/ui/PageHeader";
import { formatDateTime } from "@/lib/utils/datetime";
import type { EvaluationRunSummary, TaskInfo } from "@/schemas";

import { compareHref } from "./evaluationCompare";
import {
  agreementRate,
  evaluatorLabel,
  examplesLabel,
  modeLabel,
  runDone,
  runIsActive,
  runTimingLabel,
  triggerLabel,
} from "./evaluationDisplay";

const PAGE_SIZE = 50;
const EMPTY_TASKS: TaskInfo[] = [];
/** Runs compared at once: the compare page is A against B. */
const COMPARE_SLOTS = 2;

function RunProgress({ run }: { run: EvaluationRunSummary }) {
  const done = runDone(run);
  return (
    <div className="min-w-40">
      <div className="mb-1 flex justify-between text-xs text-base-content/60">
        <span>
          {done}/{run.total}
        </span>
        {run.pending_count > 0 && <span>{run.pending_count} pending</span>}
      </div>
      <progress className="progress progress-primary h-2" value={done} max={run.total} />
    </div>
  );
}

function RunCard({
  run,
  selected,
  selectable,
  onToggle,
}: {
  run: EvaluationRunSummary;
  /** Picked for comparison. */
  selected: boolean;
  /** Whether another run can still be picked. */
  selectable: boolean;
  onToggle: () => void;
}) {
  const agreement = agreementRate(run);
  return (
    <div className="flex items-stretch gap-2">
      <label
        className="flex shrink-0 items-center px-1"
        title={selected ? "Remove from comparison" : "Pick for comparison"}
      >
        <input
          type="checkbox"
          className="checkbox checkbox-sm"
          checked={selected}
          disabled={!selected && !selectable}
          onChange={onToggle}
          aria-label={`Compare ${run.task_name} run of ${formatDateTime(run.requested_at)}`}
        />
      </label>
      <Link
        href={`/evaluations/${run.run_id}`}
        className={`block min-w-0 flex-1 rounded-lg border bg-base-100 p-4 transition-colors hover:border-primary/50 hover:bg-base-200/40 ${
          selected ? "border-primary" : "border-base-300"
        }`}
      >
        <div className="grid gap-4 lg:grid-cols-[minmax(260px,1fr)_minmax(220px,0.8fr)_180px_32px] lg:items-center">
          <div className="min-w-0">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <span className="badge badge-neutral">{run.entity_type}</span>
              <span className="badge badge-outline">{triggerLabel(run.trigger)}</span>
              <span className="badge badge-outline">{modeLabel(run.mode)}</span>
              <span
                className={`badge badge-outline ${run.with_examples ? "badge-accent" : ""}`}
                title={
                  run.with_examples
                    ? "Labeled examples were shown before each figure"
                    : "The figure was judged against the reference alone"
                }
              >
                {examplesLabel(run.with_examples)}
              </span>
              {run.failed_count > 0 && (
                <span className="badge badge-error">{run.failed_count} failed</span>
              )}
              {(run.interrupted_count ?? 0) > 0 && (
                <span className="badge badge-warning">{run.interrupted_count} interrupted</span>
              )}
              {(run.cancelled_count ?? 0) > 0 && (
                <span className="badge badge-ghost">{run.cancelled_count} cancelled</span>
              )}
              {runIsActive(run) && <span className="badge badge-info">running</span>}
            </div>
            <div className="truncate text-sm font-medium text-base-content">{run.task_name}</div>
            <div className="mt-1 flex flex-wrap gap-2 text-xs text-base-content/60">
              <span>{run.chip_id}</span>
              {run.date && <span>{run.date}</span>}
              <span className="font-mono">{run.model || "model not recorded"}</span>
              <span>by {run.requested_by || "-"}</span>
            </div>
            {run.evaluator && (
              <div className="mt-1 truncate font-mono text-xs text-base-content/40">
                {evaluatorLabel(run.evaluator)}
              </div>
            )}
          </div>
          <div>
            <div className="mb-2 flex flex-wrap gap-2">
              {run.completed_count === 0 ? (
                <span className="badge badge-ghost">No results yet</span>
              ) : (
                <>
                  <span className="badge badge-success gap-1" title="Diagnoses reporting success">
                    <strong>{run.success_count}</strong> success
                  </span>
                  <span className="badge badge-ghost gap-1" title="Diagnoses with all six keys">
                    <strong>{run.complete_count}</strong> complete
                  </span>
                  {agreement !== null && (
                    <span
                      className="badge badge-outline gap-1"
                      title="People agreeing with the model"
                    >
                      <strong>{Math.round(agreement * 100)}%</strong> agreed ·{" "}
                      {run.agree_count + run.disagree_count} judged
                    </span>
                  )}
                </>
              )}
            </div>
            <div className="flex flex-wrap gap-x-2 text-xs text-base-content/50">
              <span>Requested {formatDateTime(run.requested_at)}</span>
              {runTimingLabel(run) && <span>{runTimingLabel(run)}</span>}
            </div>
          </div>
          <RunProgress run={run} />
          <ChevronRight className="hidden h-5 w-5 text-base-content/40 lg:block" />
        </div>
      </Link>
    </div>
  );
}

/** The runs picked for comparison, and the way to the compare page once there are two. */
function CompareBar({
  selected,
  runs,
  onClear,
}: {
  selected: string[];
  runs: EvaluationRunSummary[];
  onClear: () => void;
}) {
  const picked = selected
    .map((runId) => runs.find((run) => run.run_id === runId))
    .filter((run): run is EvaluationRunSummary => run !== undefined);
  const ready = picked.length === COMPARE_SLOTS;
  const sameSelection =
    ready && picked[0].chip_id === picked[1].chip_id && picked[0].task_name === picked[1].task_name;
  return (
    <div
      className="mb-4 flex flex-wrap items-center gap-3 rounded-lg border border-primary/40 bg-primary/5 px-4 py-2"
      data-testid="compare-bar"
    >
      <span className="text-sm">
        <strong>{picked.length}</strong> of {COMPARE_SLOTS} runs picked
        {picked.length > 0 && (
          <span className="ml-2 text-xs text-base-content/60">
            {picked
              .map((run) => `${run.task_name} (${formatDateTime(run.requested_at)})`)
              .join(" vs ")}
          </span>
        )}
      </span>
      {ready && !sameSelection && (
        <span className="text-xs text-warning">
          Different chips or tasks: entities will not line up.
        </span>
      )}
      <span className="ml-auto flex gap-2">
        <button type="button" className="btn btn-ghost btn-sm" onClick={onClear}>
          Clear
        </button>
        {ready ? (
          <Link
            href={compareHref(picked[0].run_id, picked[1].run_id)}
            className="btn btn-primary btn-sm gap-1"
          >
            <ArrowLeftRight className="h-4 w-4" />
            Compare
          </Link>
        ) : (
          <button type="button" className="btn btn-primary btn-sm gap-1" disabled>
            <ArrowLeftRight className="h-4 w-4" />
            Compare
          </button>
        )}
      </span>
    </div>
  );
}

/** Evaluation runs of the project, newest first, filtered by chip and task. */
export function EvaluationRunsPageContent() {
  const { data: taskFileSettings } = useGetTaskFileSettings();
  const defaultBackend = taskFileSettings?.data?.default_backend || "qubex";
  const { data: taskInfoData } = useListTaskInfo({ backend: defaultBackend });
  const [chipId, setChipId] = useState("");
  const [taskName, setTaskName] = useState("");
  // Runs picked for comparison, in pick order (A, then B).
  const [selected, setSelected] = useState<string[]>([]);
  const toggleSelected = (runId: string) =>
    setSelected((current) =>
      current.includes(runId)
        ? current.filter((id) => id !== runId)
        : current.length < COMPARE_SLOTS
          ? [...current, runId]
          : current,
    );

  const params = useMemo(
    () => ({
      chip_id: chipId || undefined,
      task: taskName || undefined,
      limit: PAGE_SIZE,
    }),
    [chipId, taskName],
  );
  const {
    data: response,
    isLoading,
    isError,
  } = useListEvaluationRuns(params, {
    query: {
      refetchInterval: (query) => (query.state.data?.data.runs.some(runIsActive) ? 10_000 : false),
    },
  });
  const runs = response?.data.runs ?? [];
  const tasks = taskInfoData?.data?.tasks ?? EMPTY_TASKS;

  return (
    <PageContainer maxWidth>
      <PageHeader
        title="AI Evaluations"
        description="Runs of the evaluation model over task results, with your agreement recorded per evaluation"
        actions={
          <span className="badge badge-neutral gap-1">
            <strong>{runs.length}</strong> runs
          </span>
        }
      />

      {selected.length > 0 && (
        <CompareBar selected={selected} runs={runs} onClear={() => setSelected([])} />
      )}

      <div className="mb-4 rounded-lg border border-base-300 bg-base-100 p-3">
        <PageFiltersBar>
          <PageFiltersBar.Group>
            <PageFiltersBar.Item label="Chip" className="sm:w-72">
              <div className="flex items-center gap-2">
                <div className="min-w-0 flex-1">
                  <ChipSelector selectedChip={chipId} onChipSelect={setChipId} />
                </div>
                {chipId && (
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm btn-square"
                    onClick={() => setChipId("")}
                    title="Clear chip filter"
                  >
                    <XCircle className="h-4 w-4" />
                  </button>
                )}
              </div>
            </PageFiltersBar.Item>
            <PageFiltersBar.Item label="Task" className="sm:w-80">
              <div className="flex items-center gap-2">
                <div className="min-w-0 flex-1">
                  <TaskSelector tasks={tasks} selectedTask={taskName} onTaskSelect={setTaskName} />
                </div>
                {taskName && (
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm btn-square"
                    onClick={() => setTaskName("")}
                    title="Clear task filter"
                  >
                    <XCircle className="h-4 w-4" />
                  </button>
                )}
              </div>
            </PageFiltersBar.Item>
          </PageFiltersBar.Group>
        </PageFiltersBar>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16">
          <span className="loading loading-spinner loading-lg" />
        </div>
      ) : isError ? (
        <div className="alert alert-error">
          <XCircle className="h-5 w-5" />
          <span>Failed to load evaluation runs.</span>
        </div>
      ) : runs.length === 0 ? (
        <EmptyState
          title="No evaluation runs"
          description="Start one from the chip page (Evaluate) or from a task result."
          emoji="robot"
        />
      ) : (
        <div className="space-y-3">
          {runs.map((run) => (
            <RunCard
              key={run.run_id}
              run={run}
              selected={selected.includes(run.run_id)}
              selectable={selected.length < COMPARE_SLOTS}
              onToggle={() => toggleSelected(run.run_id)}
            />
          ))}
        </div>
      )}
    </PageContainer>
  );
}
