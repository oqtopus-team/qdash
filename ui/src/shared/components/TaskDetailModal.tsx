"use client";

import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useState } from "react";

import type { Task } from "@/schemas";

import { TaskFigure } from "@/app/components/TaskFigure";

const PlotlyRenderer = dynamic(
  () => import("@/app/components/PlotlyRenderer").then((mod) => mod.default),
  { ssr: false },
);

interface TaskDetailModalProps {
  isOpen: boolean;
  task: Task | null;
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
  task,
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

  if (!isOpen || !task) return null;

  const showDateNavigation =
    selectedDate && onNavigatePrevious && onNavigateNext && formatDate;
  const showDetailView = chipId;

  const formatDateTime = (dateStr?: string | null) => {
    if (!dateStr) return "-";
    const date = new Date(dateStr);
    return (
      <>
        <div className="font-medium">
          {date.toLocaleDateString("ja-JP", {
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
          })}
        </div>
        <div className="text-xs text-base-content/60">
          {date.toLocaleTimeString("ja-JP", {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          })}
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

  return (
    <dialog className="modal modal-open">
      <div className="modal-box max-w-6xl w-11/12 max-h-[90vh] p-6 rounded-2xl shadow-xl bg-base-100 overflow-y-auto">
        <div className="flex justify-between items-center mb-6">
          <h3 className="font-bold text-xl">
            {variant === "detailed" && taskName
              ? `Task Details - ${taskName}`
              : `Result for QID ${qid}`}
          </h3>
          <div className="flex items-center gap-2">
            {getStatusBadge(task.status)}
            {showDateNavigation && (
              <>
                <button
                  onClick={onNavigatePrevious}
                  disabled={!canNavigatePrevious}
                  className="btn btn-sm btn-ghost"
                  title="Previous Day"
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
                  title="Next Day"
                >
                  →
                </button>
              </>
            )}
            {showDetailView && (
              <button
                onClick={() => router.push(`/chip/${chipId}/qubit/${qid}`)}
                className="btn btn-sm btn-primary"
                title="Detailed Analysis"
              >
                Detail View
              </button>
            )}
            <button
              onClick={onClose}
              className="btn btn-sm btn-circle btn-ghost"
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
                <div className="text-sm">{formatDateTime(task.start_at)}</div>
              </div>
            )}
            {task.end_at && (
              <div>
                <div className="text-sm text-base-content/60 mb-1">
                  End Time
                </div>
                <div className="text-sm">{formatDateTime(task.end_at)}</div>
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
                            {new Date(task.end_at).toLocaleString()}
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
                              };
                              return (
                                <tr key={key}>
                                  <td className="font-medium">{key}</td>
                                  <td className="font-mono">
                                    {typeof paramValue.value === "number"
                                      ? paramValue.value.toFixed(precision)
                                      : String(paramValue.value)}
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

                {/* Input Parameters */}
                {task.input_parameters && (
                  <div className="mb-6">
                    <h4 className="text-lg font-semibold mb-3">
                      Input Parameters
                    </h4>
                    <div className="overflow-x-auto">
                      <table className="table table-zebra table-sm">
                        <thead>
                          <tr>
                            <th>Parameter</th>
                            <th>Value</th>
                            <th>Unit</th>
                          </tr>
                        </thead>
                        <tbody>
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
                              };
                              return (
                                <tr key={key}>
                                  <td className="font-medium">{key}</td>
                                  <td className="font-mono">
                                    {typeof paramValue.value === "number"
                                      ? paramValue.value.toFixed(precision)
                                      : typeof paramValue.value === "object"
                                        ? JSON.stringify(paramValue.value)
                                        : String(paramValue.value)}
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
          <div className="w-full h-[70vh] flex flex-col justify-center items-center space-y-4">
            <div className="w-[70vw] h-full bg-base-200 rounded-xl p-4 shadow flex justify-center items-center">
              <div className="w-full h-full flex justify-center items-center">
                <div className="w-fit h-fit m-auto">
                  <PlotlyRenderer
                    className="w-full h-full"
                    fullPath={`${
                      process.env.NEXT_PUBLIC_API_URL
                    }/api/executions/figure?path=${encodeURIComponent(
                      currentJsonFigure,
                    )}`}
                  />
                </div>
              </div>
            </div>
            {jsonFigures.length > 1 && (
              <div className="flex justify-center gap-2">
                <button
                  className="btn btn-xs"
                  onClick={() =>
                    setSubIndex(
                      (subIndex - 1 + jsonFigures.length) % jsonFigures.length,
                    )
                  }
                >
                  ◀
                </button>
                <span className="text-sm">
                  {subIndex + 1} / {jsonFigures.length}
                </span>
                <button
                  className="btn btn-xs"
                  onClick={() =>
                    setSubIndex((subIndex + 1) % jsonFigures.length)
                  }
                >
                  ▶
                </button>
              </div>
            )}
          </div>
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
        <button onClick={onClose}>close</button>
      </form>
    </dialog>
  );
}
