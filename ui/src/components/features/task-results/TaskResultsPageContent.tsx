"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
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
import { PageFiltersBar } from "@/components/ui/PageFiltersBar";
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
      className={`cursor-pointer align-top hover ${isSelected ? "bg-primary/10" : ""}`}
      onClick={onSelect}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect();
        }
      }}
    >
      <td>
        <span className={`badge badge-sm ${statusBadgeClass(item.status)}`}>{item.status}</span>
      </td>
      <td className="min-w-52">
        <Link
          href={`/task-results/${item.task_id}`}
          className="inline-flex max-w-full items-center gap-1 font-medium text-primary hover:underline"
          onClick={(event) => event.stopPropagation()}
        >
          <span className="truncate">{item.task_name || "Unnamed"}</span>
          <ArrowUpRight className="h-3 w-3 shrink-0" />
        </Link>
        <div className="mt-1 font-mono text-xs text-base-content/45">{compactId(item.task_id)}</div>
      </td>
      <td>
        {item.qid ? (
          <QubitTile qid={item.qid} />
        ) : (
          <span className="text-xs text-base-content/50">-</span>
        )}
        <div className="mt-1 text-xs text-base-content/50">{item.chip_id || "-"}</div>
      </td>
      <td className="min-w-44">
        <Link
          href={`/execution/${encodeURIComponent(item.chip_id)}/${encodeURIComponent(item.execution_id)}`}
          className="font-mono text-xs text-primary hover:underline"
        >
          {compactId(item.execution_id)}
        </Link>
        <div className="mt-1 text-xs text-base-content/50">{item.username || "-"}</div>
      </td>
      <td className="min-w-36 text-xs">
        <div>{formatDateTime(item.start_at)}</div>
        <div className="mt-1 text-base-content/50">{item.elapsed_time || "-"}</div>
      </td>
      <td className="min-w-80">
        {message ? (
          <div className="flex gap-2">
            {isFailure ? (
              <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-base-content/40" />
            ) : (
              <MessageSquareText className="mt-0.5 h-3.5 w-3.5 shrink-0 text-base-content/35" />
            )}
            <div>
              <div
                className={`line-clamp-2 text-xs ${isFailure ? "text-base-content/70" : "text-base-content/60"}`}
              >
                {message}
              </div>
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
}: {
  chipId: string;
  selectedExecutionId: string;
  onExecutionSelect: (executionId: string) => void;
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
      placeholder="Select an execution"
      className="text-base-content"
      styles={styles}
      isDisabled={!chipId}
      isClearable
    />
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
    filters.chipId ||
    filters.taskName ||
    filters.qid ||
    filters.executionId ||
    filters.username ||
    filters.message;

  return (
    <PageContainer maxWidth>
      <PageHeader
        title="Task Results"
        description="Outcomes of every task across executions"
        actions={
          <span className="badge badge-neutral gap-1">
            <strong>{data?.total ?? 0}</strong> results
          </span>
        }
      />

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="tabs tabs-boxed">
          {STATUS_TABS.map((status) => (
            <button
              key={status}
              type="button"
              className={`tab tab-sm ${filters.status === status ? "tab-active" : ""}`}
              onClick={() => navigateWithFilters({ ...filters, status })}
            >
              {status === "all" ? "All" : status.charAt(0).toUpperCase() + status.slice(1)}
              {status !== "all" && data?.status_counts?.[status] != null && (
                <span className="ml-1 text-xs opacity-70">{data.status_counts[status]}</span>
              )}
            </button>
          ))}
        </div>
        {isFetching && (
          <span className="inline-flex items-center gap-1 text-xs text-base-content/50">
            <RefreshCw className="h-3.5 w-3.5 animate-spin" />
            Refreshing
          </span>
        )}
      </div>

      <form onSubmit={handleSubmit}>
        <PageFiltersBar className="mb-4 sm:mb-6">
          <PageFiltersBar.Group className="flex-1">
            <PageFiltersBar.Item label="Chip" className="sm:w-72">
              <div className="flex items-center gap-2">
                <div className="min-w-0 flex-1">
                  <ChipSelector
                    selectedChip={draftFilters.chipId}
                    onChipSelect={(chipId) =>
                      setDraftFilters((current) => ({ ...current, chipId, executionId: "" }))
                    }
                  />
                </div>
                {draftFilters.chipId && (
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm btn-square"
                    onClick={() =>
                      setDraftFilters((current) => ({ ...current, chipId: "", executionId: "" }))
                    }
                    title="Clear chip filter"
                  >
                    <XCircle className="h-4 w-4" />
                  </button>
                )}
              </div>
            </PageFiltersBar.Item>
            <PageFiltersBar.Item label="Execution" className="sm:w-72">
              <div className="flex items-center gap-2">
                <div className="min-w-0 flex-1">
                  <ExecutionFilter
                    chipId={draftFilters.chipId}
                    selectedExecutionId={draftFilters.executionId}
                    onExecutionSelect={(executionId) =>
                      setDraftFilters((current) => ({ ...current, executionId }))
                    }
                  />
                </div>
                {draftFilters.executionId && (
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm btn-square"
                    onClick={() => setDraftFilters((current) => ({ ...current, executionId: "" }))}
                    title="Clear execution filter"
                  >
                    <XCircle className="h-4 w-4" />
                  </button>
                )}
              </div>
            </PageFiltersBar.Item>
            <PageFiltersBar.Item label="Task" className="sm:w-72">
              <div className="flex items-center gap-2">
                <div className="min-w-0 flex-1">
                  <TaskSelector
                    tasks={tasks}
                    selectedTask={draftFilters.taskName}
                    onTaskSelect={(taskName) =>
                      setDraftFilters((current) => ({ ...current, taskName }))
                    }
                    disabled={tasks.length === 0}
                  />
                </div>
                {draftFilters.taskName && (
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm btn-square"
                    onClick={() => setDraftFilters((current) => ({ ...current, taskName: "" }))}
                    title="Clear task filter"
                  >
                    <XCircle className="h-4 w-4" />
                  </button>
                )}
              </div>
            </PageFiltersBar.Item>
          </PageFiltersBar.Group>
          <PageFiltersBar.Group position="end">
            <button
              type="button"
              className={`btn btn-sm gap-1 ${showMoreFilters ? "btn-neutral" : "btn-ghost"}`}
              aria-expanded={showMoreFilters}
              aria-controls="task-result-more-filters"
              onClick={() => setShowMoreFilters((value) => !value)}
            >
              <SlidersHorizontal className="h-4 w-4" />
              More filters
              {(filters.qid || filters.message || filters.username) && (
                <span className="badge badge-xs badge-primary">Active</span>
              )}
              <ChevronDown
                className={`h-3.5 w-3.5 transition-transform ${showMoreFilters ? "rotate-180" : ""}`}
              />
            </button>
            <button type="submit" className="btn btn-primary btn-sm">
              Apply
            </button>
            {hasFilters && (
              <button type="button" className="btn btn-ghost btn-sm gap-1" onClick={clearFilters}>
                <XCircle className="h-4 w-4" />
                Clear
              </button>
            )}
          </PageFiltersBar.Group>
        </PageFiltersBar>
        {showMoreFilters && (
          <div
            id="task-result-more-filters"
            className="mb-6 grid gap-3 rounded-box border border-base-300 bg-base-200/40 p-4 sm:grid-cols-[minmax(8rem,12rem)_minmax(16rem,1fr)]"
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
                <Search className="h-3.5 w-3.5 text-base-content/40" />
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

      {isError ? (
        <div className="alert alert-error">
          <XCircle className="h-5 w-5" />
          <span>Failed to load task results.</span>
        </div>
      ) : isLoading ? (
        <div className="flex justify-center py-16">
          <span className="loading loading-spinner loading-lg" />
        </div>
      ) : !data || data.items.length === 0 ? (
        <EmptyState
          title="No task results found"
          description="Try changing the status or clearing one of the filters."
          emoji="magnifying-glass"
        />
      ) : (
        <>
          <div className="mb-3 text-xs text-base-content/50">
            Showing {skip + 1}-{Math.min(skip + data.items.length, data.total)} of {data.total}
          </div>
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
