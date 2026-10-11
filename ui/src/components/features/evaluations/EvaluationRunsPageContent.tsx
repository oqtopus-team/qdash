"use client";

import { ChevronRight, XCircle } from "lucide-react";
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

import {
  agreementRate,
  evaluatorLabel,
  modeLabel,
  runDone,
  runIsActive,
  triggerLabel,
} from "./evaluationDisplay";

const PAGE_SIZE = 50;
const EMPTY_TASKS: TaskInfo[] = [];

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

function RunCard({ run }: { run: EvaluationRunSummary }) {
  const agreement = agreementRate(run);
  return (
    <Link
      href={`/evaluations/${run.run_id}`}
      className="block rounded-lg border border-base-300 bg-base-100 p-4 transition-colors hover:border-primary/50 hover:bg-base-200/40"
    >
      <div className="grid gap-4 lg:grid-cols-[minmax(260px,1fr)_minmax(220px,0.8fr)_180px_32px] lg:items-center">
        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <span className="badge badge-neutral">{run.entity_type}</span>
            <span className="badge badge-outline">{triggerLabel(run.trigger)}</span>
            <span className="badge badge-outline">{modeLabel(run.mode)}</span>
            {run.with_examples && (
              <span
                className="badge badge-accent badge-outline"
                title="Labeled examples were shown before each figure"
              >
                examples
              </span>
            )}
            {run.failed_count > 0 && (
              <span className="badge badge-error">{run.failed_count} failed</span>
            )}
            {runIsActive(run) && <span className="badge badge-info">running</span>}
          </div>
          <div className="truncate text-sm font-semibold text-base-content">{run.task_name}</div>
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
                <span className="badge badge-ghost gap-1" title="Answers parsed as JSON">
                  <strong>{run.parsed_count}</strong> parsed
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
          <div className="text-xs text-base-content/50">
            Requested {formatDateTime(run.requested_at)}
          </div>
        </div>
        <RunProgress run={run} />
        <ChevronRight className="hidden h-5 w-5 text-base-content/40 lg:block" />
      </div>
    </Link>
  );
}

/** Evaluation runs of the project, newest first, filtered by chip and task. */
export function EvaluationRunsPageContent() {
  const { data: taskFileSettings } = useGetTaskFileSettings();
  const defaultBackend = taskFileSettings?.data?.default_backend || "qubex";
  const { data: taskInfoData } = useListTaskInfo({ backend: defaultBackend });
  const [chipId, setChipId] = useState("");
  const [taskName, setTaskName] = useState("");

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
        description="Runs of the calibration evaluation model over task results. Open a run to read each evaluation, see what the model saw, and record whether you agree."
        actions={
          <span className="badge badge-neutral gap-1">
            <strong>{runs.length}</strong> runs
          </span>
        }
      />

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
            <RunCard key={run.run_id} run={run} />
          ))}
        </div>
      )}
    </PageContainer>
  );
}
