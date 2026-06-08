"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import {
  AlertCircle,
  ArrowUpRight,
  ExternalLink,
  RefreshCw,
  Search,
  X,
  XCircle,
} from "lucide-react";
import Select from "react-select";
import type { SingleValue } from "react-select";

import { useListExecutions } from "@/client/execution/execution";
import { useGetTaskResult } from "@/client/task/task";
import { useGetTaskFileSettings, useListTaskInfo } from "@/client/task-file/task-file";
import { useListTaskResults } from "@/client/task-result/task-result";
import { TaskFigure } from "@/components/charts/TaskFigure";
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

function statusBadgeClass(status: string): string {
  if (status === "completed" || status === "success") return "badge-success";
  if (status === "failed") return "badge-error";
  if (status === "running") return "badge-info";
  if (status === "scheduled" || status === "pending") return "badge-warning";
  if (status === "cancelled") return "badge-neutral";
  return "badge-ghost";
}

function compactId(value: string): string {
  if (!value) return "-";
  return value.length > 16 ? `${value.slice(0, 8)}...${value.slice(-4)}` : value;
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

  return (
    <tr
      role="button"
      tabIndex={0}
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
          className="inline-flex max-w-full items-center gap-1 font-semibold text-primary hover:underline"
          onClick={(event) => event.stopPropagation()}
        >
          <span className="truncate">{item.task_name || "Unnamed"}</span>
          <ArrowUpRight className="h-3 w-3 shrink-0" />
        </Link>
        <div className="mt-1 font-mono text-xs text-base-content/45">{compactId(item.task_id)}</div>
      </td>
      <td>
        <div className="font-mono text-xs">{item.qid || "-"}</div>
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
            <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-error" />
            <div>
              <div className="line-clamp-2 text-xs text-base-content/80">{message}</div>
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

  const { styles } = useSelectStyles<ExecutionOption>({
    labels: options.map((option) => option.label),
    placeholder: "Select an execution",
  });

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

function compactParameterValue(value: unknown): string {
  if (value === null || value === undefined) return "-";
  if (typeof value === "object" && "value" in (value as Record<string, unknown>)) {
    const record = value as Record<string, unknown>;
    const unit = typeof record.unit === "string" ? record.unit : "";
    return `${String(record.value ?? "-")}${unit ? ` ${unit}` : ""}`;
  }
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function ParameterPreview({
  title,
  parameters,
  maxItems = 6,
}: {
  title: string;
  parameters: Record<string, unknown> | undefined;
  maxItems?: number;
}) {
  const allEntries = Object.entries(parameters ?? {});
  const entries = allEntries.slice(0, maxItems);
  if (entries.length === 0) return null;

  return (
    <div className="rounded-lg border border-base-300">
      <div className="border-b border-base-300 px-3 py-2 text-xs font-semibold text-base-content/70">
        {title}
      </div>
      <dl className="divide-y divide-base-200">
        {entries.map(([key, value]) => {
          const formattedValue = compactParameterValue(value);
          return (
            <div
              key={key}
              className="grid grid-cols-[minmax(120px,0.8fr)_1fr] gap-3 px-3 py-2 text-xs"
            >
              <dt className="truncate font-mono text-base-content/55" title={key}>
                {key}
              </dt>
              <dd className="truncate font-mono text-base-content/80" title={formattedValue}>
                {formattedValue}
              </dd>
            </div>
          );
        })}
      </dl>
      {allEntries.length > maxItems && (
        <div className="border-t border-base-300 px-3 py-2 text-xs text-base-content/45">
          +{allEntries.length - maxItems} more on full page
        </div>
      )}
    </div>
  );
}

function TaskResultPreviewSidebar({
  taskId,
  onClose,
}: {
  taskId: string | null;
  onClose: () => void;
}) {
  const {
    data: response,
    isLoading,
    isError,
  } = useGetTaskResult(taskId ?? "", {
    query: { enabled: !!taskId },
  });
  const taskResult = response?.data;
  const isOpen = !!taskId;
  const figures = taskResult && Array.isArray(taskResult.figure_path) ? taskResult.figure_path : [];
  const jsonFigures =
    taskResult && Array.isArray(taskResult.json_figure_path) ? taskResult.json_figure_path : [];

  return (
    <div
      className={`fixed right-0 top-0 z-50 h-full w-full overflow-y-auto border-l border-base-300 bg-base-100 p-4 shadow-xl transition-transform duration-300 sm:w-3/4 sm:p-6 lg:w-2/5 ${
        isOpen ? "translate-x-0" : "translate-x-full"
      }`}
    >
      <button
        type="button"
        onClick={onClose}
        className="btn btn-ghost btn-sm btn-circle absolute right-3 top-3 sm:right-4 sm:top-4"
        aria-label="Close task result preview"
      >
        <X className="h-4 w-4" />
      </button>

      {taskId && (
        <div className="pr-8">
          <div className="mb-5">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              {taskResult?.status && (
                <span className={`badge badge-sm ${statusBadgeClass(taskResult.status)}`}>
                  {taskResult.status}
                </span>
              )}
              {taskResult?.qid && (
                <span className="badge badge-sm badge-neutral">{taskResult.qid}</span>
              )}
            </div>
            <h2 className="text-xl font-bold">{taskResult?.task_name || "Task Result"}</h2>
            <p className="mt-1 font-mono text-xs text-base-content/50">{taskId}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Link href={`/task-results/${taskId}`} className="btn btn-primary btn-sm gap-1">
                <ExternalLink className="h-3.5 w-3.5" />
                Open full page
              </Link>
              {taskResult?.chip_id && taskResult?.execution_id && (
                <Link
                  href={`/execution/${encodeURIComponent(taskResult.chip_id)}/${encodeURIComponent(
                    taskResult.execution_id,
                  )}`}
                  className="btn btn-ghost btn-sm gap-1"
                >
                  <ExternalLink className="h-3.5 w-3.5" />
                  Execution
                </Link>
              )}
            </div>
          </div>

          {isLoading ? (
            <div className="flex justify-center py-12">
              <span className="loading loading-spinner loading-lg" />
            </div>
          ) : isError || !taskResult ? (
            <div className="alert alert-error">
              <XCircle className="h-5 w-5" />
              <span>Failed to load task result.</span>
            </div>
          ) : (
            <div className="space-y-4">
              {(figures.length > 0 || jsonFigures.length > 0) && (
                <div>
                  <h3 className="mb-2 text-sm font-semibold">Figures</h3>
                  <div className="flex h-56 items-center gap-3 overflow-x-auto rounded-lg bg-base-200/60 p-3">
                    {figures.length > 0 ? (
                      figures.map((figure, index) => (
                        <TaskFigure
                          key={`${figure}-${index}`}
                          path={figure}
                          jsonFigurePath={jsonFigures[index]}
                          qid={taskResult.qid}
                          className="h-full w-auto shrink-0 rounded object-contain"
                        />
                      ))
                    ) : (
                      <TaskFigure
                        jsonFigurePath={jsonFigures[0]}
                        qid={taskResult.qid}
                        className="h-full w-auto shrink-0 rounded object-contain"
                      />
                    )}
                  </div>
                </div>
              )}

              <div className="rounded-lg bg-base-200/60 p-3">
                <h3 className="mb-2 text-sm font-semibold">Metadata</h3>
                <dl className="grid grid-cols-2 gap-3 text-xs">
                  <div>
                    <dt className="text-base-content/50">Chip</dt>
                    <dd className="font-mono">{taskResult.chip_id || "-"}</dd>
                  </div>
                  <div>
                    <dt className="text-base-content/50">QID</dt>
                    <dd className="font-mono">{taskResult.qid || "-"}</dd>
                  </div>
                  <div>
                    <dt className="text-base-content/50">Execution</dt>
                    <dd className="font-mono" title={taskResult.execution_id}>
                      {compactId(taskResult.execution_id)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-base-content/50">User</dt>
                    <dd>{taskResult.username || taskResult.user_id || "-"}</dd>
                  </div>
                  <div>
                    <dt className="text-base-content/50">Started</dt>
                    <dd>{formatDateTime(taskResult.start_at)}</dd>
                  </div>
                  <div>
                    <dt className="text-base-content/50">Elapsed</dt>
                    <dd>{taskResult.elapsed_time || "-"}</dd>
                  </div>
                </dl>
              </div>

              {taskResult.message ? (
                <div className="overflow-hidden rounded-lg border border-error/40">
                  <div className="flex items-center gap-2 bg-error/10 px-3 py-2 text-sm font-semibold text-error">
                    <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                    Error Log
                  </div>
                  <pre className="whitespace-pre-wrap break-all bg-error/5 px-3 py-3 font-mono text-xs text-error/80">
                    {taskResult.message}
                  </pre>
                </div>
              ) : (
                <div className="rounded-lg border border-base-300 p-3 text-sm text-base-content/60">
                  No error message recorded.
                </div>
              )}

              {taskResult.stack_trace && (
                <div className="overflow-hidden rounded-lg border border-error/30">
                  <div className="bg-error/5 px-3 py-2 text-xs font-semibold text-error/70">
                    Stack Trace
                  </div>
                  <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-all bg-error/5 px-3 py-3 font-mono text-xs text-error/60">
                    {taskResult.stack_trace}
                  </pre>
                </div>
              )}

              <ParameterPreview
                title="Output Parameters"
                parameters={taskResult.output_parameters as Record<string, unknown> | undefined}
              />
              <ParameterPreview
                title="Input Parameters"
                parameters={taskResult.input_parameters as Record<string, unknown> | undefined}
                maxItems={4}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

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
        description="Review task outcomes across executions and focus on failed results."
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
            <PageFiltersBar.Item label="Chip" className="sm:min-w-40">
              <div className="flex items-center gap-2">
                <ChipSelector
                  selectedChip={draftFilters.chipId}
                  onChipSelect={(chipId) =>
                    setDraftFilters((current) => ({ ...current, chipId, executionId: "" }))
                  }
                />
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
            <PageFiltersBar.Item label="Execution" className="sm:min-w-52">
              <div className="flex items-center gap-2">
                <ExecutionFilter
                  chipId={draftFilters.chipId}
                  selectedExecutionId={draftFilters.executionId}
                  onExecutionSelect={(executionId) =>
                    setDraftFilters((current) => ({ ...current, executionId }))
                  }
                />
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
            <PageFiltersBar.Item label="Task" className="sm:min-w-56">
              <div className="flex items-center gap-2">
                <TaskSelector
                  tasks={tasks}
                  selectedTask={draftFilters.taskName}
                  onTaskSelect={(taskName) =>
                    setDraftFilters((current) => ({ ...current, taskName }))
                  }
                  disabled={tasks.length === 0}
                />
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
            <PageFiltersBar.Item label="QID" className="sm:min-w-32">
              <input
                className="input input-bordered h-[38px] min-h-[38px] w-full"
                value={draftFilters.qid}
                onChange={(event) =>
                  setDraftFilters((current) => ({ ...current, qid: event.target.value }))
                }
                placeholder="0 or 0-1"
              />
            </PageFiltersBar.Item>
            <PageFiltersBar.Item label="Message" className="sm:min-w-72">
              <label className="input input-bordered flex h-[38px] min-h-[38px] items-center gap-2">
                <Search className="h-3.5 w-3.5 text-base-content/40" />
                <input
                  className="grow"
                  value={draftFilters.message}
                  onChange={(event) =>
                    setDraftFilters((current) => ({ ...current, message: event.target.value }))
                  }
                  placeholder="Search error message"
                />
              </label>
            </PageFiltersBar.Item>
          </PageFiltersBar.Group>
          <PageFiltersBar.Group position="end">
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
                  <th>Error Message</th>
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
