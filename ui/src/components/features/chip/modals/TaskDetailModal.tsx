"use client";

import { useRouter } from "next/navigation";
import { useState, useEffect, useRef, useCallback } from "react";
import {
  CheckCircle,
  AlertTriangle,
  Clock,
  HelpCircle,
  GitBranch,
} from "lucide-react";

import type { Task } from "@/schemas";

import { useGetTaskResult } from "@/client/task/task";
import { InteractiveFigureContent } from "@/components/charts/InteractiveFigureContent";
import { TaskFigure } from "@/components/charts/TaskFigure";
import {
  formatDate as formatDateUtil,
  formatTime as formatTimeUtil,
  formatDateTime as formatDateTimeUtil,
} from "@/utils/datetime";

interface TaskDetailModalProps {
  isOpen: boolean;
  task?: Task | null;
  qid: string;
  onClose: () => void;
  chipId?: string;
  selectedDate?: string;
  onNavigatePrevious?: () => void;
  onNavigateNext?: () => void;
  canNavigatePrevious?: boolean;
  canNavigateNext?: boolean;
  formatDate?: (date: string) => string;
  initialSubIndex?: number;
  // Enhanced props for detailed view
  taskId?: string;
  taskName?: string;
  variant?: "simple" | "detailed";
}

export function TaskDetailModal({
  isOpen,
  task: taskProp,
  qid,
  onClose,
  chipId,
  selectedDate,
  onNavigatePrevious,
  onNavigateNext,
  canNavigatePrevious,
  canNavigateNext,
  formatDate,
  initialSubIndex = 0,
  taskId,
  taskName,
  variant = "simple",
}: TaskDetailModalProps) {
  const router = useRouter();
  const [viewMode, setViewMode] = useState<"static" | "interactive">("static");
  const [subIndex, setSubIndex] = useState(initialSubIndex);
  const modalRef = useRef<HTMLDialogElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  const resolveQid = (taskQid: string, qidRole?: string): string => {
    if (!qidRole || qidRole === "self" || qidRole === "coupling")
      return taskQid;
    const match = taskQid.match(/^(\d+)-(\d+)$/);
    if (!match) return taskQid;
    const [, control, target] = match;
    if (qidRole === "control") return control;
    if (qidRole === "target") return target;
    return taskQid;
  };

  const buildProvenanceUrl = (parameterName: string, qidValue: string) => {
    const p = encodeURIComponent(parameterName);
    const q = encodeURIComponent(qidValue);
    return `/provenance?tab=lineage&parameter=${p}&qid=${q}`;
  };

  // Handle keyboard navigation
  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    },
    [onClose],
  );

  // Focus management and keyboard handling
  useEffect(() => {
    if (isOpen) {
      // Focus the close button when modal opens
      closeButtonRef.current?.focus();
      // Add keyboard listener
      document.addEventListener("keydown", handleKeyDown);
      // Prevent body scroll
      document.body.style.overflow = "hidden";
    }

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "";
    };
  }, [isOpen, handleKeyDown]);

  // Use generated API client hook when taskId is provided
  const {
    data: fetchedResponse,
    isLoading: loading,
    error: fetchError,
  } = useGetTaskResult(taskId!, {
    query: {
      enabled: isOpen && !!taskId && !taskProp,
    },
  });

  // Extract data from AxiosResponse and convert to Task format
  const fetchedTaskData = fetchedResponse?.data;
  const fetchedTask: Task | null = fetchedTaskData
    ? ({
        task_id: fetchedTaskData.task_id,
        name: fetchedTaskData.task_name,
        qid: fetchedTaskData.qid,
        status: fetchedTaskData.status,
        figure_path: fetchedTaskData.figure_path,
        json_figure_path: fetchedTaskData.json_figure_path,
        input_parameters: fetchedTaskData.input_parameters,
        output_parameters: fetchedTaskData.output_parameters,
        start_at: fetchedTaskData.start_at,
        end_at: fetchedTaskData.end_at,
        elapsed_time: fetchedTaskData.elapsed_time,
      } as Task)
    : null;

  const task = taskProp || fetchedTask;
  const error = (fetchError as Error)?.message || null;

  if (!isOpen) return null;

  // Loading state
  if (loading) {
    return (
      <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 backdrop-blur-sm">
        <div className="bg-base-100 rounded-xl p-8">
          <span className="loading loading-spinner loading-lg"></span>
          <p className="mt-4 text-center">Loading task details...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 backdrop-blur-sm p-4">
        <div className="bg-base-100 rounded-xl p-8 max-w-md">
          <div className="alert alert-error">
            <span>Error: {error}</span>
          </div>
          <button onClick={onClose} className="btn btn-primary mt-4 w-full">
            Close
          </button>
        </div>
      </div>
    );
  }

  if (!task) return null;

  const showDateNavigation =
    selectedDate && onNavigatePrevious && onNavigateNext && formatDate;
  const showDetailView = chipId;

  const formatDateTimeLocal = (dateStr?: string | null) => {
    if (!dateStr) return "-";
    return (
      <>
        <div className="font-medium">{formatDateUtil(dateStr)}</div>
        <div className="text-xs text-base-content/60">
          {formatTimeUtil(dateStr)}
        </div>
      </>
    );
  };

  const figures = Array.isArray(task.figure_path)
    ? task.figure_path
    : task.figure_path
      ? [task.figure_path]
      : [];
  const currentFigure = figures[subIndex] || null;

  const jsonFigures = task.json_figure_path
    ? Array.isArray(task.json_figure_path)
      ? task.json_figure_path
      : [task.json_figure_path]
    : [];
  const currentJsonFigure = jsonFigures[subIndex] || null;

  const getStatusBadge = (status?: string) => {
    switch (status) {
      case "completed":
        return <span className="badge badge-success badge-sm">Completed</span>;
      case "failed":
        return <span className="badge badge-error badge-sm">Failed</span>;
      default:
        return <span className="badge badge-warning badge-sm">Pending</span>;
    }
  };

  const precision = variant === "detailed" ? 6 : 4;

  const modalTitle =
    variant === "detailed" && taskName
      ? `Task Details - ${taskName}`
      : `Result for QID ${qid}`;

  return (
    <dialog
      ref={modalRef}
      className="modal modal-open"
      aria-labelledby="modal-title"
      aria-modal="true"
      role="dialog"
    >
      <div className="modal-box w-fit min-w-[500px] max-w-[95vw] h-fit max-h-[95vh] p-6 rounded-2xl shadow-xl bg-base-100 overflow-y-auto">
        <div className="flex justify-between items-center mb-6">
          <h3 id="modal-title" className="font-bold text-xl">
            {modalTitle}
          </h3>
          <div className="flex items-center gap-2">
            {getStatusBadge(task.status)}
            {showDateNavigation && (
              <>
                <button
                  onClick={onNavigatePrevious}
                  disabled={!canNavigatePrevious}
                  className="btn btn-sm btn-ghost"
                  aria-label="Go to previous day"
                >
                  ←
                </button>
                <span className="text-sm text-base-content/70 px-2">
                  {formatDate!(selectedDate!)}
                </span>
                <button
                  onClick={onNavigateNext}
                  disabled={!canNavigateNext}
                  className="btn btn-sm btn-ghost"
                  aria-label="Go to next day"
                >
                  →
                </button>
              </>
            )}
            {showDetailView && (
              <button
                onClick={() => router.push(`/chip/${chipId}/qubit/${qid}`)}
                className="btn btn-sm btn-primary"
                aria-label="Open detailed analysis view"
              >
                Detail View
              </button>
            )}
            <button
              ref={closeButtonRef}
              onClick={onClose}
              className="btn btn-sm btn-circle btn-ghost"
              aria-label="Close modal"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Task Information (detailed variant only) */}
        {variant === "detailed" && (
          <div className="grid grid-cols-2 gap-4 mb-6">
            {taskId && (
              <div>
                <div className="text-sm text-base-content/60 mb-1">Task ID</div>
                <div className="font-mono text-sm break-all">{taskId}</div>
              </div>
            )}
            {taskName && (
              <div>
                <div className="text-sm text-base-content/60 mb-1">
                  Task Name
                </div>
                <div className="font-medium">{taskName}</div>
              </div>
            )}
            {task.start_at && (
              <div>
                <div className="text-sm text-base-content/60 mb-1">
                  Start Time
                </div>
                <div className="text-sm">
                  {formatDateTimeLocal(task.start_at)}
                </div>
              </div>
            )}
            {task.end_at && (
              <div>
                <div className="text-sm text-base-content/60 mb-1">
                  End Time
                </div>
                <div className="text-sm">
                  {formatDateTimeLocal(task.end_at)}
                </div>
              </div>
            )}
            {task.elapsed_time && (
              <div>
                <div className="text-sm text-base-content/60 mb-1">
                  Duration
                </div>
                <div className="font-medium">{task.elapsed_time}</div>
              </div>
            )}
          </div>
        )}

        {viewMode === "static" && (
          <>
            {/* Figures */}
            {figures.length > 0 && (
              <div className="mb-6">
                <h4 className="text-lg font-semibold mb-3">
                  Figures ({figures.length})
                </h4>
                {variant === "detailed" ? (
                  /* Detailed view: 2-column grid */
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {figures.map((path, idx) => (
                      <div
                        key={idx}
                        className="bg-base-200 rounded-lg p-4 overflow-hidden"
                      >
                        <div className="text-sm text-base-content/60 mb-2">
                          Figure {idx + 1}
                        </div>
                        <div className="bg-white rounded-lg p-2">
                          <TaskFigure
                            path={path}
                            qid={qid}
                            className="w-full h-auto max-h-[400px] object-contain"
                          />
                        </div>
                        {jsonFigures[idx] && (
                          <div className="mt-2 flex justify-center">
                            <button
                              className="btn btn-xs btn-primary"
                              onClick={() => {
                                setSubIndex(idx);
                                setViewMode("interactive");
                              }}
                            >
                              Interactive View
                            </button>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  /* Simple view: single column with navigation */
                  <div className="grid grid-cols-2 gap-8">
                    <div className="aspect-square bg-base-200/50 rounded-xl p-4">
                      {currentFigure && (
                        <TaskFigure
                          path={currentFigure}
                          qid={qid}
                          className="w-full h-full object-contain"
                        />
                      )}
                      {figures.length > 1 && (
                        <div className="flex justify-center mt-2 gap-2">
                          <button
                            className="btn btn-xs"
                            onClick={() =>
                              setSubIndex(
                                (subIndex - 1 + figures.length) %
                                  figures.length,
                              )
                            }
                          >
                            ◀
                          </button>
                          <span className="text-sm">
                            {subIndex + 1} / {figures.length}
                          </span>
                          <button
                            className="btn btn-xs"
                            onClick={() =>
                              setSubIndex((subIndex + 1) % figures.length)
                            }
                          >
                            ▶
                          </button>
                        </div>
                      )}
                      {task.json_figure_path && (
                        <button
                          className="btn btn-sm mt-4"
                          onClick={() => setViewMode("interactive")}
                        >
                          Interactive View
                        </button>
                      )}
                    </div>
                    <div className="space-y-6">
                      {/* Simple view: right column with info */}
                      <div className="card bg-base-200 p-4 rounded-xl">
                        <h4 className="font-medium mb-2">Status</h4>
                        <div
                          className={`badge ${
                            task.status === "completed"
                              ? "badge-success"
                              : task.status === "failed"
                                ? "badge-error"
                                : "badge-warning"
                          }`}
                        >
                          {task.status}
                        </div>
                      </div>
                      {task.end_at && (
                        <div className="card bg-base-200 p-4 rounded-xl">
                          <h4 className="font-medium mb-2">Calibrated At</h4>
                          <p className="text-sm">
                            {formatDateTimeUtil(task.end_at)}
                          </p>
                        </div>
                      )}
                      {task.output_parameters && (
                        <div className="card bg-base-200 p-4 rounded-xl">
                          <h4 className="font-medium mb-2">Parameters</h4>
                          <div className="space-y-2">
                            {Object.entries(task.output_parameters).map(
                              ([key, value]) => {
                                const paramValue = (
                                  typeof value === "object" &&
                                  value !== null &&
                                  "value" in value
                                    ? value
                                    : { value }
                                ) as { value: number | string; unit?: string };
                                return (
                                  <div
                                    key={key}
                                    className="flex justify-between"
                                  >
                                    <span className="font-medium">{key}:</span>
                                    <span>
                                      {typeof paramValue.value === "number"
                                        ? paramValue.value.toFixed(precision)
                                        : String(paramValue.value)}
                                      {paramValue.unit
                                        ? ` ${paramValue.unit}`
                                        : ""}
                                    </span>
                                  </div>
                                );
                              },
                            )}
                          </div>
                        </div>
                      )}
                      {task.message && (
                        <div className="card bg-base-200 p-4 rounded-xl">
                          <h4 className="font-medium mb-2">Message</h4>
                          <p className="text-sm">{task.message}</p>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Parameters Tables (detailed variant only) */}
            {variant === "detailed" && (
              <>
                {/* Output Parameters */}
                {task.output_parameters && (
                  <div className="mb-6">
                    <h4 className="text-lg font-semibold mb-3">
                      Output Parameters
                    </h4>
                    <div className="overflow-x-auto">
                      <table className="table table-zebra table-sm">
                        <thead>
                          <tr>
                            <th>Parameter</th>
                            <th>Value</th>
                            <th>Error</th>
                            <th>Unit</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(task.output_parameters).map(
                            ([key, value]) => {
                              const paramValue = (
                                typeof value === "object" &&
                                value !== null &&
                                "value" in value
                                  ? value
                                  : { value }
                              ) as {
                                value: number | string;
                                unit?: string;
                                error?: number;
                                description?: string;
                              };
                              return (
                                <tr
                                  key={key}
                                  title={paramValue.description || undefined}
                                >
                                  <td className="font-medium">{key}</td>
                                  <td className="font-mono">
                                    {typeof paramValue.value === "number"
                                      ? paramValue.value.toFixed(precision)
                                      : String(paramValue.value)}
                                  </td>
                                  <td className="font-mono text-base-content/70">
                                    {paramValue.error !== undefined &&
                                    paramValue.error !== 0
                                      ? `±${paramValue.error.toFixed(precision)}`
                                      : "-"}
                                  </td>
                                  <td>{paramValue.unit || "-"}</td>
                                </tr>
                              );
                            },
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* Input Parameters (Calibration Dependencies) - Card View */}
                {task.input_parameters &&
                  Object.keys(task.input_parameters).length > 0 && (
                    <div className="mb-6">
                      <h4 className="text-lg font-semibold mb-3">
                        Calibration Inputs
                      </h4>
                      <div className="space-y-2">
                        {Object.entries(task.input_parameters).map(
                          ([key, value]) => {
                            const paramValue = (
                              typeof value === "object" &&
                              value !== null &&
                              "value" in value
                                ? value
                                : { value }
                            ) as {
                              value: number | string | object;
                              unit?: string;
                              error?: number;
                              description?: string;
                              execution_id?: string;
                              calibrated_at?: string;
                              task_name?: string;
                            };

                            // Calculate freshness status
                            const getFreshnessStatus = () => {
                              if (!paramValue.calibrated_at) {
                                return {
                                  status: "unknown",
                                  icon: <HelpCircle size={16} />,
                                  label: "Unknown",
                                  className: "text-base-content/50",
                                };
                              }
                              const calibratedDate = new Date(
                                paramValue.calibrated_at,
                              );
                              const now = new Date();
                              const hoursDiff =
                                (now.getTime() - calibratedDate.getTime()) /
                                (1000 * 60 * 60);

                              if (hoursDiff < 24) {
                                return {
                                  status: "fresh",
                                  icon: <CheckCircle size={16} />,
                                  label: "Fresh",
                                  className: "text-success",
                                };
                              } else if (hoursDiff < 72) {
                                return {
                                  status: "recent",
                                  icon: <Clock size={16} />,
                                  label: "Recent",
                                  className: "text-warning",
                                };
                              } else {
                                return {
                                  status: "stale",
                                  icon: <AlertTriangle size={16} />,
                                  label: "Stale",
                                  className: "text-error",
                                };
                              }
                            };

                            const freshness = getFreshnessStatus();

                            // Format relative time
                            const getRelativeTime = () => {
                              if (!paramValue.calibrated_at) return null;
                              const calibratedDate = new Date(
                                paramValue.calibrated_at,
                              );
                              const now = new Date();
                              const diffMs =
                                now.getTime() - calibratedDate.getTime();
                              const diffMins = Math.floor(diffMs / (1000 * 60));
                              const diffHours = Math.floor(
                                diffMs / (1000 * 60 * 60),
                              );
                              const diffDays = Math.floor(
                                diffMs / (1000 * 60 * 60 * 24),
                              );

                              if (diffMins < 60) return `${diffMins}m ago`;
                              if (diffHours < 24) return `${diffHours}h ago`;
                              return `${diffDays}d ago`;
                            };

                            const relativeTime = getRelativeTime();

                            return (
                              <div
                                key={key}
                                className="card card-compact bg-base-200 hover:bg-base-300 transition-colors"
                              >
                                <div className="card-body py-3 px-4">
                                  <div className="flex items-center justify-between">
                                    {/* Left: Parameter info */}
                                    <div className="flex items-center gap-3">
                                      <span
                                        className={freshness.className}
                                        title={freshness.label}
                                      >
                                        {freshness.icon}
                                      </span>
                                      <div>
                                        <div className="font-semibold text-sm">
                                          {key}
                                        </div>
                                        <div className="text-xs text-base-content/60">
                                          {paramValue.description ||
                                            "Calibration parameter"}
                                        </div>
                                      </div>
                                    </div>

                                    {/* Right: Value */}
                                    <div className="text-right">
                                      <div className="font-mono font-semibold">
                                        {typeof paramValue.value === "number"
                                          ? paramValue.value.toFixed(precision)
                                          : typeof paramValue.value === "object"
                                            ? JSON.stringify(paramValue.value)
                                            : String(paramValue.value)}{" "}
                                        <span className="text-base-content/70 font-normal">
                                          {paramValue.unit || ""}
                                        </span>
                                      </div>
                                      {paramValue.error !== undefined &&
                                        paramValue.error !== 0 && (
                                          <div className="text-xs text-base-content/50 font-mono">
                                            ±
                                            {paramValue.error.toFixed(
                                              precision,
                                            )}
                                          </div>
                                        )}
                                    </div>
                                  </div>

                                  {/* Source info */}
                                  {(paramValue.execution_id ||
                                    relativeTime) && (
                                    <div className="flex items-center justify-between mt-2 pt-2 border-t border-base-300">
                                      <div className="flex items-center gap-2 text-xs text-base-content/60">
                                        <span>↳ from</span>
                                        {paramValue.execution_id ? (
                                          <div className="dropdown dropdown-top">
                                            <button
                                              tabIndex={0}
                                              className="link link-primary"
                                            >
                                              {paramValue.task_name ||
                                                `Execution ${paramValue.execution_id.slice(0, 8)}`}
                                            </button>
                                            <ul
                                              tabIndex={0}
                                              className="dropdown-content z-[1] menu p-2 shadow-lg bg-base-100 rounded-box w-48 border border-base-300"
                                            >
                                              <li>
                                                <button
                                                  onClick={() => {
                                                    router.push(
                                                      `/executions/${paramValue.execution_id}`,
                                                    );
                                                  }}
                                                >
                                                  View Execution
                                                </button>
                                              </li>
                                              <li>
                                                <button
                                                  onClick={() => {
                                                    const parameterName =
                                                      (paramValue as any)
                                                        ?.parameter_name || key;
                                                    const resolvedQid =
                                                      resolveQid(
                                                        qid,
                                                        (paramValue as any)
                                                          ?.qid_role,
                                                      );
                                                    router.push(
                                                      buildProvenanceUrl(
                                                        parameterName,
                                                        resolvedQid,
                                                      ),
                                                    );
                                                    onClose();
                                                  }}
                                                >
                                                  View Lineage
                                                </button>
                                              </li>
                                            </ul>
                                          </div>
                                        ) : (
                                          <span>Unknown source</span>
                                        )}
                                      </div>
                                      {relativeTime && (
                                        <span
                                          className={`text-xs ${freshness.className}`}
                                        >
                                          {relativeTime}
                                        </span>
                                      )}
                                    </div>
                                  )}
                                </div>
                              </div>
                            );
                          },
                        )}
                      </div>

                      {/* Lineage Graph Button */}
                      <div className="mt-4 text-center">
                        <button
                          className="btn btn-ghost btn-sm gap-2 hover:btn-primary"
                          onClick={() => {
                            const outputs =
                              (task as any)?.output_parameters &&
                              typeof (task as any).output_parameters ===
                                "object"
                                ? Object.entries(
                                    (task as any).output_parameters,
                                  )
                                : [];
                            const inputs =
                              (task as any)?.input_parameters &&
                              typeof (task as any).input_parameters === "object"
                                ? Object.entries((task as any).input_parameters)
                                : [];

                            const [key, paramValue] =
                              (outputs[0] as any) ?? (inputs[0] as any) ?? [];

                            if (key && paramValue) {
                              const parameterName =
                                (paramValue as any)?.parameter_name || key;
                              const resolvedQid = resolveQid(
                                qid,
                                (paramValue as any)?.qid_role,
                              );
                              router.push(
                                buildProvenanceUrl(parameterName, resolvedQid),
                              );
                            } else {
                              router.push("/provenance");
                            }
                            onClose();
                          }}
                        >
                          <GitBranch size={16} />
                          Explore Provenance
                        </button>
                      </div>
                    </div>
                  )}

                {/* Message */}
                {task.message && (
                  <div>
                    <h4 className="text-lg font-semibold mb-3">Message</h4>
                    <div className="alert">
                      <span>{task.message}</span>
                    </div>
                  </div>
                )}
              </>
            )}
          </>
        )}

        {viewMode === "interactive" && currentJsonFigure && (
          <InteractiveFigureContent
            figureJsonPath={currentJsonFigure}
            figureIndex={subIndex}
            totalFigures={jsonFigures.length}
            onNavigatePrevious={() =>
              setSubIndex(
                (subIndex - 1 + jsonFigures.length) % jsonFigures.length,
              )
            }
            onNavigateNext={() =>
              setSubIndex((subIndex + 1) % jsonFigures.length)
            }
          />
        )}

        <div className="mt-6 flex justify-end gap-2">
          {viewMode === "interactive" && (
            <button
              className="btn btn-sm"
              onClick={() => setViewMode("static")}
            >
              Back to Summary
            </button>
          )}
        </div>
      </div>
      <form method="dialog" className="modal-backdrop">
        <button onClick={onClose} aria-label="Close modal">
          close
        </button>
      </form>
    </dialog>
  );
}
