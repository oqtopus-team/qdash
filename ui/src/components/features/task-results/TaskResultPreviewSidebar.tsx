"use client";

import Link from "next/link";
import { ExternalLink, X, XCircle } from "lucide-react";

import { useGetTaskFileSettings, useListTaskInfo } from "@/client/task-file/task-file";
import { useGetTaskResult } from "@/client/task/task";
import { FigureStrip } from "@/components/charts/FigureStrip";
import { TaskFigure } from "@/components/charts/TaskFigure";
import { ExecutionTaskProgress } from "@/components/features/execution/ExecutionTaskProgress";
import { TaskLineageSection } from "@/components/features/provenance/TaskLineageSection";
import { QubitTile } from "@/components/ui/QubitTile";
import { TaskMessagePanel } from "@/components/ui/TaskMessagePanel";
import { useEscapeLayer } from "@/hooks/useFullscreenPanel";
import { formatDateTime } from "@/lib/utils/datetime";
import { getTaskParameterUiGroup } from "@/lib/utils/task-parameters";

export function statusBadgeClass(status: string): string {
  if (status === "completed" || status === "success") return "badge-success";
  if (status === "failed") return "badge-error";
  if (status === "running") return "badge-info";
  if (status === "scheduled" || status === "pending") return "badge-warning";
  if (status === "cancelled") return "badge-neutral";
  return "badge-ghost";
}

export function compactId(value: string): string {
  if (!value) return "-";
  return value.length > 16 ? `${value.slice(0, 8)}...${value.slice(-4)}` : value;
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
  parameterDefinitions,
  maxItems = 6,
}: {
  title: string;
  parameters: Record<string, unknown> | undefined;
  parameterDefinitions?: Record<string, unknown>;
  maxItems?: number;
}) {
  const allEntries = Object.entries(parameters ?? {});
  const regularEntries: [string, unknown][] = [];
  const parameterGroups = new Map<string, { collapsed: boolean; entries: [string, unknown][] }>();
  for (const entry of allEntries) {
    const group = getTaskParameterUiGroup(parameterDefinitions?.[entry[0]] ?? entry[1]);
    if (!group) {
      regularEntries.push(entry);
      continue;
    }
    const existing = parameterGroups.get(group.name);
    if (existing) {
      existing.entries.push(entry);
    } else {
      parameterGroups.set(group.name, { collapsed: group.collapsed, entries: [entry] });
    }
  }
  const entries = regularEntries.slice(0, maxItems);
  if (allEntries.length === 0) return null;

  const renderEntries = (items: [string, unknown][]) => (
    <dl className="divide-y divide-base-200">
      {items.map(([key, value]) => {
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
  );

  return (
    <div className="rounded-lg border border-base-300">
      <div className="border-b border-base-300 px-3 py-2 text-xs font-medium text-base-content/70">
        {title}
      </div>
      {renderEntries(entries)}
      {regularEntries.length > maxItems && (
        <div className="border-t border-base-300 px-3 py-2 text-xs text-base-content/45">
          +{regularEntries.length - maxItems} more on full page
        </div>
      )}
      {[...parameterGroups.entries()].map(([groupName, group]) => (
        <details
          key={groupName}
          className="collapse collapse-arrow rounded-none border-t border-base-300 bg-base-100"
          open={!group.collapsed}
        >
          <summary className="collapse-title min-h-0 px-3 py-2 text-xs font-medium">
            <span className="flex items-center gap-2">
              {groupName}
              <span className="badge badge-xs badge-ghost">{group.entries.length}</span>
            </span>
          </summary>
          <div className="collapse-content px-0 pb-0">{renderEntries(group.entries)}</div>
        </details>
      ))}
    </div>
  );
}

interface TaskResultPreviewSidebarProps {
  /** Result to preview; null keeps the sidebar closed. */
  taskId: string | null;
  onClose: () => void;
  /** Hide the link to the execution page when the sidebar already sits on that page. */
  showExecutionLink?: boolean;
}

/**
 * Slide-over preview of one task result, shared by every page that lets the user pick a result
 * in place (a Task Results row, an Execution Flow node).
 *
 * Fetches the full result for `taskId` and shows its figures, metadata, message and a trimmed
 * set of parameters; the full page at `/task-results/[taskId]` has the rest.
 */
export function TaskResultPreviewSidebar({
  taskId,
  onClose,
  showExecutionLink = true,
}: TaskResultPreviewSidebarProps) {
  const isOpen = !!taskId;
  const {
    data: response,
    isLoading,
    isError,
  } = useGetTaskResult(taskId ?? "", {
    query: {
      enabled: isOpen,
      refetchInterval: (query) => {
        const status = query.state.data?.data.status;
        return status === "running" || status === "scheduled" || status === "pending"
          ? 2000
          : false;
      },
      refetchIntervalInBackground: true,
    },
  });
  const taskResult = response?.data;
  const { data: taskFileSettings } = useGetTaskFileSettings({ query: { enabled: isOpen } });
  const defaultBackend = taskFileSettings?.data?.default_backend || "qubex";
  const { data: taskInfoData } = useListTaskInfo(
    { backend: defaultBackend },
    { query: { enabled: isOpen } },
  );
  const taskDefinition = taskInfoData?.data?.tasks.find(
    (task) => task.name === taskResult?.task_name,
  );
  const figures = taskResult && Array.isArray(taskResult.figure_path) ? taskResult.figure_path : [];
  const jsonFigures =
    taskResult && Array.isArray(taskResult.json_figure_path) ? taskResult.json_figure_path : [];

  // Escape closes the preview first, then any fullscreen panel it was opened over.
  useEscapeLayer(isOpen, onClose);

  return (
    <div
      role="complementary"
      aria-label="Task result preview"
      aria-hidden={!isOpen}
      inert={!isOpen}
      className={`fixed right-0 top-0 z-[70] h-full w-full overflow-y-auto border-l border-base-300 bg-base-100 p-4 shadow-xl transition-transform duration-300 sm:w-3/4 sm:p-6 lg:w-2/5 ${
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
              {taskResult?.qid && <QubitTile qid={taskResult.qid} />}
            </div>
            <h2 className="text-sm font-medium">{taskResult?.task_name || "Task result"}</h2>
            {taskResult && (
              <ExecutionTaskProgress status={taskResult.status} note={taskResult.note} />
            )}
            <p className="mt-1 font-mono text-xs text-base-content/50">{taskId}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Link href={`/task-results/${taskId}`} className="btn btn-primary btn-sm gap-1">
                <ExternalLink className="h-3.5 w-3.5" />
                Open full page
              </Link>
              {showExecutionLink && taskResult?.chip_id && taskResult?.execution_id && (
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
                  <h3 className="mb-2 text-xs font-medium text-base-content/60">Figures</h3>
                  <FigureStrip className="h-56 gap-3 rounded-lg bg-base-200/60 p-3">
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
                  </FigureStrip>
                </div>
              )}

              <div className="rounded-lg bg-base-200/60 p-3">
                <h3 className="mb-2 text-xs font-medium text-base-content/60">Metadata</h3>
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

              <TaskLineageSection
                taskId={taskId}
                executionId={taskResult.execution_id}
                qid={taskResult.qid ?? ""}
                outputParameters={
                  taskResult.output_parameters as Record<string, unknown> | undefined
                }
                className="rounded-lg bg-base-200/60 p-3"
              />

              <TaskMessagePanel
                status={taskResult.status}
                message={taskResult.message}
                stackTrace={taskResult.stack_trace}
                showEmptyFallback
              />

              <ParameterPreview
                title="Output Parameters"
                parameters={taskResult.output_parameters as Record<string, unknown> | undefined}
              />
              <ParameterPreview
                title="Input Parameters"
                parameters={taskResult.input_parameters as Record<string, unknown> | undefined}
                parameterDefinitions={taskDefinition?.input_parameters}
                maxItems={4}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
