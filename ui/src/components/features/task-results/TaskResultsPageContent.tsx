"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  AlertCircle,
  ArrowUpRight,
  ChevronDown,
  MessageSquareText,
  RefreshCw,
  Search,
  SlidersHorizontal,
  XCircle,
} from "lucide-react";
import Select from "react-select";
import type { SingleValue } from "react-select";

import { useListExecutions } from "@/client/execution/execution";
import { useGetTaskFileSettings, useListTaskInfo } from "@/client/task-file/task-file";
import { useListTaskResults } from "@/client/task-result/task-result";
import { ChipSelector } from "@/components/selectors/ChipSelector";
import { TaskSelector } from "@/components/selectors/TaskSelector";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { useSelectStyles } from "@/hooks/useSelectStyles";
import { formatDateTime } from "@/lib/utils/datetime";
import type {
  ExecutionResponseSummary,
  ListTaskResultsParams,
  TaskInfo,
  TaskResultListItem,
} from "@/schemas";
import { QubitTile } from "@/components/ui/QubitTile";
import {
  TaskResultPreviewSidebar,
  compactId,
  statusBadgeClass,
} from "@/components/features/task-results/TaskResultPreviewSidebar";

const PAGE_SIZE = 50;
const STATUS_TABS = ["all", "failed", "running", "completed", "cancelled"] as const;
const EMPTY_TASKS: TaskInfo[] = [];

type FilterState = {
  status: string;
  chipId: string;
  taskName: string;
  qid: string;
  executionId: string;
  username: string;
  message: string;
};

type SearchParamReader = {
  get(name: string): string | null;
  toString(): string;
};

type ExecutionOption = {
  value: string;
  label: string;
};

function readFilters(searchParams: SearchParamReader): FilterState {
  return {
    status: searchParams.get("status") || "all",
    chipId: searchParams.get("chip_id") || "",
    taskName: searchParams.get("task_name") || "",
    qid: searchParams.get("qid") || "",
    executionId: searchParams.get("execution_id") || "",
    username: searchParams.get("username") || "",
    message: searchParams.get("message_contains") || "",
  };
}

function isFailureStatus(status: string): boolean {
  return status === "failed";
}

function executionOptionLabel(execution: ExecutionResponseSummary): string {
  const started = formatDateTime(execution.start_at, "MM/dd HH:mm");
  return `${execution.name || "Execution"} / ${execution.status} / ${started} / ${compactId(
    execution.execution_id,
  )}`;
}

function updateParamsFromFilters(
  searchParams: SearchParamReader,
  filters: FilterState,
  skip: number,
): URLSearchParams {
  const next = new URLSearchParams(searchParams.toString());
  const entries: Array<[string, string]> = [
    ["status", filters.status === "all" ? "" : filters.status],
    ["chip_id", filters.chipId],
    ["task_name", filters.taskName],
    ["qid", filters.qid],
    ["execution_id", filters.executionId],
    ["username", filters.username],
    ["message_contains", filters.message],
    ["skip", skip > 0 ? String(skip) : ""],
  ];
  for (const [key, value] of entries) {
    const trimmed = value.trim();
    if (trimmed) {
      next.set(key, trimmed);
    } else {
      next.delete(key);
    }
  }
  return next;
}

function TaskResultRow({
  item,
  isSelected,
  onSelect,
}: {
  item: TaskResultListItem;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const message = item.message?.trim();
  const isFailure = isFailureStatus(item.status);

  return (
    <tr
      role="button"
      tabIndex={0}
      aria-label={`Preview ${item.task_name || "unnamed"} task result for ${item.qid || "unknown target"}`}
      aria-current={isSelected ? "true" : undefined}
      className={`cursor-pointer align-top focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary ${isSelected ? "bg-primary/10" : ""}`}
      onClick={onSelect}
      onKeyDown={(event) => {
        if (event.target !== event.currentTarget) return;
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect();
        }
      }}
    >
      <td className="whitespace-nowrap">
        <span className={`badge badge-sm ${statusBadgeClass(item.status)}`}>{item.status}</span>
      </td>
      <td className="min-w-40 max-w-64">
        <Link
          href={`/task-results/${item.task_id}`}
          className="inline-flex max-w-full items-center gap-1 font-medium text-primary hover:underline"
          onClick={(event) => event.stopPropagation()}
        >
          <span className="truncate">{item.task_name || "Unnamed"}</span>
          <ArrowUpRight className="h-3 w-3 shrink-0" aria-hidden="true" />
        </Link>
        <div className="mt-0.5 font-mono text-xs text-base-content/60">
          {compactId(item.task_id)}
        </div>
      </td>
      <td className="whitespace-nowrap">
        {item.qid ? (
          <QubitTile qid={item.qid} />
        ) : (
          <span className="text-xs text-base-content/60">-</span>
        )}
        <div className="mt-0.5 font-mono text-xs text-base-content/60">{item.chip_id || "-"}</div>
      </td>
      <td className="whitespace-nowrap">
        <Link
          href={`/execution/${encodeURIComponent(item.chip_id)}/${encodeURIComponent(item.execution_id)}`}
          className="font-mono text-xs text-primary hover:underline"
          onClick={(event) => event.stopPropagation()}
        >
          {compactId(item.execution_id)}
        </Link>
        <div className="mt-0.5 text-xs text-base-content/60">{item.username || "-"}</div>
      </td>
      <td className="whitespace-nowrap">
        <div className="font-mono text-xs">{formatDateTime(item.start_at)}</div>
        <div className="mt-0.5 font-mono text-xs text-base-content/60">
          {item.elapsed_time || "-"}
        </div>
      </td>
      <td className="min-w-64">
        {message ? (
          <div className="flex gap-2">
            {isFailure ? (
              <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-error" aria-hidden="true" />
            ) : (
              <MessageSquareText
                className="mt-0.5 h-3.5 w-3.5 shrink-0 text-base-content/40"
                aria-hidden="true"
              />
            )}
            <div className="min-w-0">
              <div className="line-clamp-2 text-xs text-base-content/70 break-words">{message}</div>
              {item.has_stack_trace && (
                <span className="badge badge-xs badge-outline mt-1">Stack trace</span>
              )}
            </div>
          </div>
        ) : (
          <span className="text-xs text-base-content/40">No message</span>
        )}
      </td>
    </tr>
  );
}

/**
 * Dropdown for filtering task results by execution within a selected chip
 */
function ExecutionFilter({
  chipId,
  selectedExecutionId,
  onExecutionSelect,
  inputId,
}: {
  chipId: string;
  selectedExecutionId: string;
  onExecutionSelect: (executionId: string) => void;
  inputId?: string;
}) {
  const { data: executionData, isLoading } = useListExecutions(
    { chip_id: chipId || "__none__", skip: 0, limit: 100 },
    {
      query: {
        enabled: !!chipId,
        staleTime: 30_000,
      },
    },
  );

  const options = useMemo<ExecutionOption[]>(() => {
    const executions = executionData?.data?.executions ?? [];
    const items = executions.map((execution) => ({
      value: execution.execution_id,
      label: executionOptionLabel(execution),
    }));
    if (selectedExecutionId && !items.some((item) => item.value === selectedExecutionId)) {
      items.unshift({
        value: selectedExecutionId,
        label: `Current filter / ${compactId(selectedExecutionId)}`,
      });
    }
    return items;
  }, [executionData?.data?.executions, selectedExecutionId]);

  const styles = useSelectStyles<ExecutionOption>();

  if (isLoading) {
    return <div className="h-[38px] animate-pulse rounded bg-base-300" />;
  }

  const handleChange = (option: SingleValue<ExecutionOption>) => {
    onExecutionSelect(option?.value ?? "");
  };

  return (
    <Select<ExecutionOption>
      options={options}
      value={options.find((option) => option.value === selectedExecutionId) ?? null}
      onChange={handleChange}
      placeholder={chipId ? "Select an execution" : "Select a chip first"}
      className="text-base-content"
      styles={styles}
      inputId={inputId}
      isDisabled={!chipId}
      isClearable
    />
  );
}

/**
 * Labelled filter field with an optional inline clear button
 */
function FilterField({
  id,
  label,
  clearLabel,
  onClear,
  children,
}: {
  id: string;
  label: string;
  clearLabel: string;
  onClear?: () => void;
  children: ReactNode;
}) {
  return (
    <div className="min-w-0">
      <label htmlFor={id} className="mb-1 block text-xs font-medium text-base-content/60">
        {label}
      </label>
      <div className="flex items-center gap-1">
        <div className="min-w-0 flex-1">{children}</div>
        {onClear && (
          <button
            type="button"
            className="btn btn-ghost btn-sm btn-square"
            onClick={onClear}
            aria-label={clearLabel}
            title={clearLabel}
          >
            <XCircle className="h-4 w-4" aria-hidden="true" />
          </button>
        )}
      </div>
    </div>
  );
}

function filtersEqual(a: FilterState, b: FilterState): boolean {
  return (Object.keys(a) as Array<keyof FilterState>).every(
    (key) => a[key].trim() === b[key].trim(),
  );
}

/**
 * Task results page listing outcomes across executions with filters and a preview sidebar
 */
export function TaskResultsPageContent() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { data: taskFileSettings } = useGetTaskFileSettings();
  const defaultBackend = taskFileSettings?.data?.default_backend || "qubex";
  const { data: taskInfoData } = useListTaskInfo({ backend: defaultBackend });
  const filters = useMemo(() => readFilters(searchParams), [searchParams]);
  const [draftFilters, setDraftFilters] = useState<FilterState>(filters);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [showMoreFilters, setShowMoreFilters] = useState(
    () => !!filters.qid || !!filters.message || !!filters.username,
  );
  const skip = Number(searchParams.get("skip") || 0);
  const tasks = taskInfoData?.data?.tasks ?? EMPTY_TASKS;

  useEffect(() => {
    setDraftFilters(filters);
  }, [filters]);

  const params: ListTaskResultsParams = useMemo(
    () => ({
      status: filters.status === "all" ? undefined : filters.status,
      chip_id: filters.chipId || undefined,
      task_name: filters.taskName || undefined,
      qid: filters.qid || undefined,
      execution_id: filters.executionId || undefined,
      username: filters.username || undefined,
      message_contains: filters.message || undefined,
      skip,
      limit: PAGE_SIZE,
    }),
    [filters, skip],
  );

  const {
    data: response,
    isLoading,
    isError,
    isFetching,
  } = useListTaskResults(params, {
    query: { staleTime: 15_000 },
  });
  const data = response?.data;
  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / PAGE_SIZE));
  const currentPage = Math.floor(skip / PAGE_SIZE) + 1;

  const navigateWithFilters = (nextFilters: FilterState, nextSkip = 0) => {
    const next = updateParamsFromFilters(searchParams, nextFilters, nextSkip);
    router.push(`${pathname}${next.toString() ? `?${next.toString()}` : ""}`);
    setDraftFilters(nextFilters);
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    navigateWithFilters(draftFilters);
  };

  const clearFilters = () => {
    const empty = {
      status: "all",
      chipId: "",
      taskName: "",
      qid: "",
      executionId: "",
      username: "",
      message: "",
    };
    navigateWithFilters(empty);
  };

  const hasFilters =
    filters.status !== "all" ||
    !!filters.chipId ||
    !!filters.taskName ||
    !!filters.qid ||
    !!filters.executionId ||
    !!filters.username ||
    !!filters.message;
  const hasPendingChanges = !filtersEqual(draftFilters, filters);

  const rangeLabel =
    data && data.items.length > 0
      ? `Showing ${skip + 1}-${Math.min(skip + data.items.length, data.total)} of ${data.total}`
      : data
        ? `${data.total} results`
        : null;

  return (
    <PageContainer maxWidth>
      <PageHeader title="Task Results" description="Outcomes of every task across executions" />

      <form onSubmit={handleSubmit} aria-label="Task result filters" className="mb-4">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-[repeat(3,minmax(0,18rem))_1fr] xl:items-end">
          <FilterField
            id="task-result-filter-chip"
            label="Chip"
            clearLabel="Clear chip filter"
            onClear={
              draftFilters.chipId
                ? () => setDraftFilters((current) => ({ ...current, chipId: "", executionId: "" }))
                : undefined
            }
          >
            <ChipSelector
              inputId="task-result-filter-chip"
              selectedChip={draftFilters.chipId}
              onChipSelect={(chipId) =>
                setDraftFilters((current) => ({ ...current, chipId, executionId: "" }))
              }
            />
          </FilterField>
          <FilterField
            id="task-result-filter-execution"
            label="Execution"
            clearLabel="Clear execution filter"
            onClear={
              draftFilters.executionId
                ? () => setDraftFilters((current) => ({ ...current, executionId: "" }))
                : undefined
            }
          >
            <ExecutionFilter
              inputId="task-result-filter-execution"
              chipId={draftFilters.chipId}
              selectedExecutionId={draftFilters.executionId}
              onExecutionSelect={(executionId) =>
                setDraftFilters((current) => ({ ...current, executionId }))
              }
            />
          </FilterField>
          <FilterField
            id="task-result-filter-task"
            label="Task"
            clearLabel="Clear task filter"
            onClear={
              draftFilters.taskName
                ? () => setDraftFilters((current) => ({ ...current, taskName: "" }))
                : undefined
            }
          >
            <TaskSelector
              inputId="task-result-filter-task"
              tasks={tasks}
              selectedTask={draftFilters.taskName}
              onTaskSelect={(taskName) => setDraftFilters((current) => ({ ...current, taskName }))}
              disabled={tasks.length === 0}
            />
          </FilterField>
          <div className="flex min-h-[38px] flex-wrap items-center gap-2 sm:col-span-2 xl:col-span-1 xl:justify-end">
            {hasPendingChanges && (
              <span className="text-xs text-base-content/60" role="status">
                Unapplied changes
              </span>
            )}
            <button
              type="button"
              className={`btn btn-sm gap-1 ${showMoreFilters ? "btn-neutral" : "btn-ghost"}`}
              aria-expanded={showMoreFilters}
              aria-controls="task-result-more-filters"
              onClick={() => setShowMoreFilters((value) => !value)}
            >
              <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
              More filters
              {(filters.qid || filters.message || filters.username) && (
                <span className="badge badge-xs badge-primary">Active</span>
              )}
              <ChevronDown
                className={`h-3.5 w-3.5 transition-transform ${showMoreFilters ? "rotate-180" : ""}`}
                aria-hidden="true"
              />
            </button>
            <button type="submit" className="btn btn-primary btn-sm">
              Apply
            </button>
            {(hasFilters || hasPendingChanges) && (
              <button type="button" className="btn btn-ghost btn-sm gap-1" onClick={clearFilters}>
                <XCircle className="h-4 w-4" aria-hidden="true" />
                Clear
              </button>
            )}
          </div>
        </div>
        {showMoreFilters && (
          <div
            id="task-result-more-filters"
            className="mt-3 grid gap-3 rounded-box border border-base-300 bg-base-200/40 p-4 sm:grid-cols-[minmax(8rem,12rem)_minmax(16rem,1fr)]"
          >
            <label className="form-control">
              <span className="mb-1 text-xs font-medium text-base-content/60">QID</span>
              <input
                className="input input-bordered h-[38px] min-h-[38px] w-full bg-base-100"
                value={draftFilters.qid}
                onChange={(event) =>
                  setDraftFilters((current) => ({ ...current, qid: event.target.value }))
                }
                placeholder="0 or 0-1"
              />
            </label>
            <label className="form-control">
              <span className="mb-1 text-xs font-medium text-base-content/60">
                Message contains
              </span>
              <span className="input input-bordered flex h-[38px] min-h-[38px] items-center gap-2 bg-base-100">
                <Search className="h-3.5 w-3.5 text-base-content/40" aria-hidden="true" />
                <input
                  className="grow"
                  value={draftFilters.message}
                  onChange={(event) =>
                    setDraftFilters((current) => ({ ...current, message: event.target.value }))
                  }
                  placeholder="Search result messages"
                />
              </span>
            </label>
          </div>
        )}
      </form>

      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
        <div
          className="tabs tabs-boxed w-fit max-w-full overflow-x-auto"
          role="group"
          aria-label="Status"
        >
          {STATUS_TABS.map((status) => (
            <button
              key={status}
              type="button"
              aria-pressed={filters.status === status}
              className={`tab tab-sm ${filters.status === status ? "tab-active" : ""}`}
              onClick={() => navigateWithFilters({ ...filters, status })}
            >
              {status === "all" ? "All" : status.charAt(0).toUpperCase() + status.slice(1)}
              {status !== "all" && data?.status_counts?.[status] != null && (
                <span className="ml-1 font-mono text-xs opacity-70">
                  {data.status_counts[status]}
                </span>
              )}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-3 text-xs text-base-content/60" aria-live="polite">
          {isFetching && !isLoading && (
            <span className="inline-flex items-center gap-1">
              <RefreshCw className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
              Refreshing
            </span>
          )}
          {rangeLabel && !isError && <span className="font-mono">{rangeLabel}</span>}
        </div>
      </div>

      {isError ? (
        <div className="alert alert-error">
          <XCircle className="h-5 w-5" aria-hidden="true" />
          <span>Failed to load task results.</span>
        </div>
      ) : isLoading ? (
        <div className="flex justify-center py-16">
          <span className="loading loading-spinner loading-lg" />
        </div>
      ) : !data || data.items.length === 0 ? (
        hasFilters ? (
          <EmptyState
            title="No task results match these filters"
            description="Change the status or filters, or clear them to see every result"
            emoji="magnifying-glass"
            action={
              <button type="button" className="btn btn-sm gap-1" onClick={clearFilters}>
                <XCircle className="h-4 w-4" aria-hidden="true" />
                Clear filters
              </button>
            }
          />
        ) : (
          <EmptyState
            title="No task results yet"
            description="Results appear here after an execution runs a task"
            emoji="empty"
          />
        )
      ) : (
        <>
          <div className="overflow-x-auto rounded-lg border border-base-300 bg-base-100">
            <table className="table table-sm">
              <thead>
                <tr>
                  <th>Status</th>
                  <th>Task</th>
                  <th>Target</th>
                  <th>Execution</th>
                  <th>Started</th>
                  <th>Message</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => (
                  <TaskResultRow
                    key={item.task_id}
                    item={item}
                    isSelected={selectedTaskId === item.task_id}
                    onSelect={() => setSelectedTaskId(item.task_id)}
                  />
                ))}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="mt-6 flex items-center justify-center gap-3">
              <button
                type="button"
                className="btn btn-sm btn-ghost"
                disabled={skip === 0}
                onClick={() => navigateWithFilters(filters, Math.max(0, skip - PAGE_SIZE))}
              >
                Previous
              </button>
              <span className="text-sm text-base-content/60">
                Page {currentPage} of {totalPages}
              </span>
              <button
                type="button"
                className="btn btn-sm btn-ghost"
                disabled={currentPage >= totalPages}
                onClick={() => navigateWithFilters(filters, skip + PAGE_SIZE)}
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
      <TaskResultPreviewSidebar taskId={selectedTaskId} onClose={() => setSelectedTaskId(null)} />
    </PageContainer>
  );
}
