"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { Bot, ChevronRight, XCircle } from "lucide-react";

import { useGetCopilotConfig } from "@/client/copilot/copilot";
import { useGetTaskFileSettings, useListTaskInfo } from "@/client/task-file/task-file";
import { useListTaskResultAiReviewRuns } from "@/client/task-result/task-result";
import { ChipSelector } from "@/components/selectors/ChipSelector";
import { TaskSelector } from "@/components/selectors/TaskSelector";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageFiltersBar } from "@/components/ui/PageFiltersBar";
import { PageHeader } from "@/components/ui/PageHeader";
import { formatDateTime } from "@/lib/utils/datetime";
import type { AiReviewRunSummary, TaskInfo } from "@/schemas";

type Filters = {
  chipId: string;
  taskName: string;
  skip: number;
};

const PAGE_SIZE = 50;
const EMPTY_TASKS: TaskInfo[] = [];
const EMPTY_TASK_NAMES: string[] = [];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

// The copilot config is an untyped JSON blob; narrow it with guards
// instead of an unchecked `as` assertion (see UI guidelines §Type Assertions).
function extractAiReviewTaskNames(config: Record<string, unknown> | undefined): string[] {
  if (!isRecord(config) || !isRecord(config.analysis)) return EMPTY_TASK_NAMES;
  const taskNames = config.analysis.ai_review_tasks;
  if (!Array.isArray(taskNames)) return EMPTY_TASK_NAMES;
  return taskNames.filter((name: unknown): name is string => typeof name === "string");
}

function decisionBadgeClass(decision: string): string {
  if (decision === "FAIL" || decision === "FORMAT_ERROR") return "badge-error";
  if (decision === "REVIEW") return "badge-warning";
  if (decision === "PASS_WITH_NOTE") return "badge-info";
  if (decision === "PASS") return "badge-success";
  return "badge-ghost";
}

function RunProgress({ run }: { run: AiReviewRunSummary }) {
  const done = run.completed_count + run.failed_count;
  return (
    <div className="min-w-40">
      <div className="mb-1 flex justify-between text-xs text-base-content/60">
        <span>
          {done}/{run.total}
        </span>
        <span>{run.running_count + run.requested_count} active</span>
      </div>
      <progress className="progress progress-primary h-2" value={done} max={run.total} />
    </div>
  );
}

function RunCard({ run }: { run: AiReviewRunSummary }) {
  const decisionEntries = Object.entries(run.decision_counts ?? {});
  return (
    <Link
      href={`/ai-reviews/${run.review_run_id}`}
      className="block rounded-lg border border-base-300 bg-base-100 p-4 transition-colors hover:border-primary/50 hover:bg-base-200/40"
    >
      <div className="grid gap-4 lg:grid-cols-[minmax(260px,1fr)_minmax(220px,0.8fr)_180px_32px] lg:items-center">
        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <span className="badge badge-neutral">{run.entity_type}</span>
            <span className="badge badge-outline">{run.trigger_type}</span>
            {run.failed_count > 0 && (
              <span className="badge badge-error">{run.failed_count} failed</span>
            )}
            {run.running_count + run.requested_count > 0 && (
              <span className="badge badge-warning">
                {run.running_count + run.requested_count} running
              </span>
            )}
          </div>
          <div className="truncate text-sm font-semibold text-base-content">{run.task_name}</div>
          <div className="mt-1 flex flex-wrap gap-2 text-xs text-base-content/60">
            <span>{run.chip_id}</span>
            <span>
              {run.execution_ids.length === 1
                ? `exec ${run.execution_ids[0]}`
                : `${run.execution_ids.length} executions`}
            </span>
            <span>{run.model || "model not recorded"}</span>
            <span>by {run.requested_by || "-"}</span>
          </div>
          <div className="mt-1 font-mono text-xs text-base-content/40">{run.review_run_id}</div>
        </div>
        <div>
          <div className="mb-2 flex flex-wrap gap-2">
            {decisionEntries.length === 0 ? (
              <span className="badge badge-ghost">No decisions yet</span>
            ) : (
              decisionEntries.map(([decision, count]: [string, number]) => (
                <span key={decision} className={`badge ${decisionBadgeClass(decision)} gap-1`}>
                  <strong>{count}</strong> {decision}
                </span>
              ))
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

export function AiReviewRunsPageContent() {
  const { data: taskFileSettings } = useGetTaskFileSettings();
  const defaultBackend = taskFileSettings?.data?.default_backend || "qubex";
  const { data: taskInfoData } = useListTaskInfo({ backend: defaultBackend });
  const { data: copilotConfigResponse } = useGetCopilotConfig();
  const [filters, setFilters] = useState<Filters>({ chipId: "", taskName: "", skip: 0 });

  const params = useMemo(
    () => ({
      chip_id: filters.chipId || undefined,
      task_name: filters.taskName || undefined,
      skip: filters.skip,
      limit: PAGE_SIZE,
    }),
    [filters],
  );
  const {
    data: response,
    isLoading,
    isError,
    isFetching,
  } = useListTaskResultAiReviewRuns(params, {
    query: { staleTime: 30_000 },
  });
  const data = response?.data;
  const tasks = taskInfoData?.data?.tasks ?? EMPTY_TASKS;
  const aiReviewTaskNames = useMemo(
    () => extractAiReviewTaskNames(copilotConfigResponse?.data),
    [copilotConfigResponse?.data],
  );
  const aiReviewTasks = useMemo(() => {
    const tasksByName = new Map(tasks.map((task: TaskInfo) => [task.name, task]));
    return aiReviewTaskNames.map(
      (taskName: string) => tasksByName.get(taskName) ?? { name: taskName },
    );
  }, [aiReviewTaskNames, tasks]);
  const currentPage = Math.floor(filters.skip / PAGE_SIZE) + 1;
  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / PAGE_SIZE));

  const updateFilter = (patch: Partial<Filters>) => {
    setFilters((current) => ({ ...current, ...patch, skip: 0 }));
  };

  return (
    <PageContainer maxWidth>
      <PageHeader
        title="AI Review Runs"
        description="Browse AI review runs and open one run to inspect all targets."
        actions={
          <span className="badge badge-neutral gap-1">
            <strong>{data?.total ?? 0}</strong> runs
          </span>
        }
      />

      <div className="mb-4 rounded-lg border border-base-300 bg-base-100 p-3">
        <PageFiltersBar>
          <PageFiltersBar.Group>
            <PageFiltersBar.Item label="Chip" className="sm:min-w-56">
              <div className="flex items-center gap-2">
                <ChipSelector
                  selectedChip={filters.chipId}
                  onChipSelect={(chipId) => updateFilter({ chipId })}
                />
                {filters.chipId && (
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm btn-square"
                    onClick={() => updateFilter({ chipId: "" })}
                    title="Clear chip filter"
                  >
                    <XCircle className="h-4 w-4" />
                  </button>
                )}
              </div>
            </PageFiltersBar.Item>
            <PageFiltersBar.Item label="Task" className="sm:min-w-80">
              <div className="flex items-center gap-2">
                <TaskSelector
                  tasks={aiReviewTasks}
                  selectedTask={filters.taskName}
                  onTaskSelect={(taskName) => updateFilter({ taskName })}
                  disabled={aiReviewTasks.length === 0}
                />
                {filters.taskName && (
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm btn-square"
                    onClick={() => updateFilter({ taskName: "" })}
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

      {isError ? (
        <div className="alert alert-error">
          <XCircle className="h-5 w-5" />
          <span>Failed to load AI review runs.</span>
        </div>
      ) : isLoading ? (
        <div className="flex justify-center py-16">
          <span className="loading loading-spinner loading-lg" />
        </div>
      ) : !data || data.items.length === 0 ? (
        <EmptyState
          title="No AI review runs found"
          description="Bulk AI review runs will appear here after new reviews are requested."
          emoji="magnifying-glass"
        />
      ) : (
        <>
          <div className="mb-3 flex items-center justify-between text-xs text-base-content/50">
            <span>
              Showing {filters.skip + 1}-{Math.min(filters.skip + data.items.length, data.total)} of{" "}
              {data.total}
            </span>
            {isFetching && (
              <span className="flex items-center gap-1">
                <Bot className="h-3.5 w-3.5" />
                Refreshing
              </span>
            )}
          </div>
          <div className="space-y-3">
            {data.items.map((run: AiReviewRunSummary) => (
              <RunCard key={run.review_run_id} run={run} />
            ))}
          </div>
          {totalPages > 1 && (
            <div className="mt-6 flex items-center justify-center gap-3">
              <button
                className="btn btn-sm btn-ghost"
                disabled={filters.skip === 0}
                onClick={() =>
                  setFilters((current) => ({
                    ...current,
                    skip: Math.max(0, current.skip - PAGE_SIZE),
                  }))
                }
              >
                Previous
              </button>
              <span className="text-sm text-base-content/60">
                Page {currentPage} of {totalPages}
              </span>
              <button
                className="btn btn-sm btn-ghost"
                disabled={currentPage >= totalPages}
                onClick={() =>
                  setFilters((current) => ({
                    ...current,
                    skip: current.skip + PAGE_SIZE,
                  }))
                }
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </PageContainer>
  );
}
