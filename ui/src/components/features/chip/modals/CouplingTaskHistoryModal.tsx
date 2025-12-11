"use client";

import dynamic from "next/dynamic";
import React, { useState, useRef, useEffect } from "react";

import type { Task } from "@/schemas";

import { useGetCouplingTaskHistory } from "@/client/task-result/task-result";
import { TaskFigure } from "@/components/charts/TaskFigure";

const PlotlyRenderer = dynamic(
  () => import("@/components/charts/PlotlyRenderer").then((mod) => mod.default),
  { ssr: false },
);

interface CouplingTaskHistoryModalProps {
  chipId: string;
  couplingId: string;
  taskName: string;
  isOpen: boolean;
  onClose: () => void;
}

interface ParameterValue {
  value: unknown;
  unit?: string;
}

export function CouplingTaskHistoryModal({
  chipId,
  couplingId,
  taskName,
  isOpen,
  onClose,
}: CouplingTaskHistoryModalProps) {
  const modalRef = useRef<HTMLDialogElement>(null);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [subIndex, setSubIndex] = useState(0);
  const [viewMode, setViewMode] = useState<"static" | "interactive">("static");
  const [isFlipped, setIsFlipped] = useState(false);

  useEffect(() => {
    const modal = modalRef.current;
    if (!modal) return;

    if (isOpen && !modal.open) {
      modal.showModal();
    } else if (!isOpen && modal.open) {
      modal.close();
    }
  }, [isOpen]);

  const { data, isLoading, isError } = useGetCouplingTaskHistory(
    couplingId,
    { chip_id: chipId, task: taskName },
    {
      query: {
        enabled: isOpen && !!chipId && !!couplingId && !!taskName,
      },
    },
  );

  // Convert the data object to an array sorted by timestamp (newest first)
  const historyData = data?.data?.data || {};
  const historyArray = Object.entries(historyData)
    .map(([key, task]) => ({ key, task: task as Task }))
    .sort((a, b) => {
      const dateA = a.task.end_at ? new Date(a.task.end_at).getTime() : 0;
      const dateB = b.task.end_at ? new Date(b.task.end_at).getTime() : 0;
      return dateB - dateA;
    });

  const selectedItem = historyArray[selectedIndex];
  const selectedTask = selectedItem?.task;
  const figures = selectedTask
    ? Array.isArray(selectedTask.figure_path)
      ? selectedTask.figure_path
      : selectedTask.figure_path
        ? [selectedTask.figure_path]
        : []
    : [];
  const jsonFigures = selectedTask
    ? Array.isArray(selectedTask.json_figure_path)
      ? selectedTask.json_figure_path
      : selectedTask.json_figure_path
        ? [selectedTask.json_figure_path]
        : []
    : [];
  const currentFigure = figures[subIndex];
  const currentJsonFigure = jsonFigures[subIndex];

  // Reset subIndex when changing selected item (keep flip state)
  const handleSelectIndex = (idx: number) => {
    setSelectedIndex(idx);
    setSubIndex(0);
    setViewMode("static");
  };

  return (
    <dialog
      ref={modalRef}
      className="modal modal-bottom sm:modal-middle"
      onClose={onClose}
    >
      <div className="modal-box w-full sm:w-11/12 max-w-5xl bg-base-100 p-3 sm:p-6 max-h-[85vh] sm:max-h-[90vh]">
        <div className="flex justify-between items-center mb-3 sm:mb-4">
          <h3 className="font-bold text-base sm:text-lg truncate pr-2">
            {taskName} - {couplingId}
          </h3>
          <button
            onClick={onClose}
            className="btn btn-sm btn-circle btn-ghost flex-shrink-0"
          >
            ✕
          </button>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center h-48 sm:h-96">
            <span className="loading loading-spinner loading-lg"></span>
          </div>
        ) : isError || historyArray.length === 0 ? (
          <div className="alert alert-info text-sm">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              className="stroke-current shrink-0 w-5 h-5 sm:w-6 sm:h-6"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            <span>No history available</span>
          </div>
        ) : (
          <div className="flex flex-col lg:flex-row gap-3 sm:gap-4">
            {/* Detail View - shown first on mobile (top), second on desktop (right) */}
            <div className="order-1 lg:order-2 lg:w-2/3 flex flex-col min-h-0 overflow-y-auto">
              <div className="flex items-center justify-between mb-2 sm:mb-3 flex-shrink-0">
                <h4 className="text-sm sm:text-md font-bold">Result</h4>
                <div className="text-xs sm:text-sm text-base-content/60">
                  {selectedIndex + 1} / {historyArray.length}
                </div>
              </div>

              {/* Navigation Arrows + View Toggle */}
              <div className="flex items-center justify-between mb-2 sm:mb-3 flex-shrink-0">
                <div className="flex gap-2">
                  <button
                    className="btn btn-xs sm:btn-sm btn-ghost"
                    disabled={selectedIndex === 0}
                    onClick={() =>
                      handleSelectIndex(Math.max(0, selectedIndex - 1))
                    }
                  >
                    ← Newer
                  </button>
                  <button
                    className="btn btn-xs sm:btn-sm btn-ghost"
                    disabled={selectedIndex === historyArray.length - 1}
                    onClick={() =>
                      handleSelectIndex(
                        Math.min(historyArray.length - 1, selectedIndex + 1),
                      )
                    }
                  >
                    Older →
                  </button>
                </div>
                <button
                  className={`btn btn-xs sm:btn-sm ${isFlipped ? "btn-primary" : "btn-ghost"}`}
                  onClick={() => setIsFlipped(!isFlipped)}
                >
                  {isFlipped ? "◀ Figure" : "Parameters ▶"}
                </button>
              </div>

              {/* Figure Display - Flip Card */}
              <div className="flex-1 min-h-[180px] sm:min-h-[300px] [perspective:1000px]">
                <div
                  className={`relative w-full h-full transition-transform duration-500 [transform-style:preserve-3d] ${
                    isFlipped ? "[transform:rotateY(180deg)]" : ""
                  }`}
                >
                  {/* Front - Figure */}
                  <div className="absolute inset-0 bg-base-200 rounded-lg p-2 sm:p-4 overflow-auto [backface-visibility:hidden]">
                    {viewMode === "static" && currentFigure ? (
                      <div className="h-full flex flex-col">
                        <TaskFigure
                          path={currentFigure}
                          qid={couplingId}
                          className="w-full h-auto flex-1 object-contain"
                        />
                        <div className="flex justify-center mt-2 gap-2 items-center">
                          {figures.length > 1 && (
                            <>
                              <button
                                className="btn btn-xs"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setSubIndex(
                                    (prev) =>
                                      (prev - 1 + figures.length) %
                                      figures.length,
                                  );
                                }}
                              >
                                ◀
                              </button>
                              <span className="text-xs sm:text-sm">
                                {subIndex + 1} / {figures.length}
                              </span>
                              <button
                                className="btn btn-xs"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setSubIndex(
                                    (prev) => (prev + 1) % figures.length,
                                  );
                                }}
                              >
                                ▶
                              </button>
                            </>
                          )}
                          {currentJsonFigure && (
                            <button
                              className="btn btn-xs btn-primary ml-2"
                              onClick={(e) => {
                                e.stopPropagation();
                                setViewMode("interactive");
                              }}
                            >
                              Interactive
                            </button>
                          )}
                        </div>
                      </div>
                    ) : viewMode === "interactive" && currentJsonFigure ? (
                      <div className="h-full flex flex-col">
                        <div className="flex-1 flex justify-center items-center">
                          <PlotlyRenderer
                            className="w-full h-full"
                            fullPath={`/api/executions/figure?path=${encodeURIComponent(
                              currentJsonFigure,
                            )}`}
                          />
                        </div>
                        <div className="flex justify-center mt-2 gap-2 items-center">
                          {jsonFigures.length > 1 && (
                            <>
                              <button
                                className="btn btn-xs"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setSubIndex(
                                    (prev) =>
                                      (prev - 1 + jsonFigures.length) %
                                      jsonFigures.length,
                                  );
                                }}
                              >
                                ◀
                              </button>
                              <span className="text-xs sm:text-sm">
                                {subIndex + 1} / {jsonFigures.length}
                              </span>
                              <button
                                className="btn btn-xs"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setSubIndex(
                                    (prev) => (prev + 1) % jsonFigures.length,
                                  );
                                }}
                              >
                                ▶
                              </button>
                            </>
                          )}
                          <button
                            className="btn btn-xs btn-ghost ml-2"
                            onClick={(e) => {
                              e.stopPropagation();
                              setViewMode("static");
                            }}
                          >
                            Static
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="alert alert-warning text-sm">
                        <svg
                          xmlns="http://www.w3.org/2000/svg"
                          fill="none"
                          viewBox="0 0 24 24"
                          className="stroke-current shrink-0 w-5 h-5 sm:w-6 sm:h-6"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth="2"
                            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                          />
                        </svg>
                        <span>No figure available</span>
                      </div>
                    )}
                  </div>

                  {/* Back - Input/Output Parameters */}
                  <div className="absolute inset-0 bg-base-200 rounded-lg p-3 sm:p-4 overflow-auto [backface-visibility:hidden] [transform:rotateY(180deg)]">
                    <div className="h-full flex flex-col gap-2 text-xs">
                      {/* Input Parameters */}
                      {selectedTask?.input_parameters &&
                        Object.keys(selectedTask.input_parameters).length >
                          0 && (
                          <div className="bg-base-100 p-3 rounded-lg">
                            <h5 className="font-semibold mb-2 flex items-center gap-1">
                              <span className="text-primary">▸</span> Input
                            </h5>
                            <div className="space-y-1">
                              {Object.entries(selectedTask.input_parameters)
                                .sort(([a], [b]) => a.localeCompare(b))
                                .map(([key, value]) => {
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
                                    <div
                                      key={key}
                                      className="flex justify-between"
                                    >
                                      <span className="text-base-content/70">
                                        {key}:
                                      </span>
                                      <span className="font-medium">
                                        {typeof paramValue.value === "number"
                                          ? paramValue.value.toFixed(4)
                                          : String(paramValue.value)}
                                        {paramValue.unit
                                          ? ` ${paramValue.unit}`
                                          : ""}
                                      </span>
                                    </div>
                                  );
                                })}
                            </div>
                          </div>
                        )}

                      {/* Output Parameters */}
                      {selectedTask?.output_parameters &&
                        Object.keys(selectedTask.output_parameters).length >
                          0 && (
                          <div className="bg-base-100 p-3 rounded-lg">
                            <h5 className="font-semibold mb-2 flex items-center gap-1">
                              <span className="text-success">▸</span> Output
                            </h5>
                            <div className="space-y-1">
                              {Object.entries(selectedTask.output_parameters)
                                .sort(([a], [b]) => a.localeCompare(b))
                                .map(([key, value]) => {
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
                                    <div
                                      key={key}
                                      className="flex justify-between"
                                    >
                                      <span className="text-base-content/70">
                                        {key}:
                                      </span>
                                      <span className="font-medium">
                                        {typeof paramValue.value === "number"
                                          ? paramValue.value.toFixed(4)
                                          : String(paramValue.value)}
                                        {paramValue.unit
                                          ? ` ${paramValue.unit}`
                                          : ""}
                                      </span>
                                    </div>
                                  );
                                })}
                            </div>
                          </div>
                        )}

                      {/* No parameters */}
                      {(!selectedTask?.input_parameters ||
                        Object.keys(selectedTask.input_parameters).length ===
                          0) &&
                        (!selectedTask?.output_parameters ||
                          Object.keys(selectedTask.output_parameters).length ===
                            0) && (
                          <div className="flex-1 flex items-center justify-center text-base-content/50">
                            No parameters available
                          </div>
                        )}
                    </div>
                  </div>
                </div>
              </div>

              {/* Metadata - compact on mobile, full on desktop */}
              {selectedTask && (
                <>
                  {/* Mobile: minimal info */}
                  <div className="sm:hidden mt-2 flex items-center justify-between text-xs bg-base-200 p-2 rounded-lg">
                    <div className="flex items-center gap-2">
                      <span
                        className={`badge badge-xs ${
                          selectedTask.status === "completed"
                            ? "badge-success"
                            : selectedTask.status === "failed"
                              ? "badge-error"
                              : "badge-warning"
                        }`}
                      >
                        {selectedTask.status}
                      </span>
                      <span className="text-base-content/60">
                        {selectedTask.end_at
                          ? new Date(selectedTask.end_at).toLocaleString(
                              "ja-JP",
                              {
                                timeZone: "Asia/Tokyo",
                                month: "numeric",
                                day: "numeric",
                                hour: "2-digit",
                                minute: "2-digit",
                              },
                            )
                          : "N/A"}
                      </span>
                    </div>
                  </div>
                  {/* Desktop: full details */}
                  <div className="hidden sm:block mt-3 space-y-3">
                    {/* Status */}
                    <div className="text-xs bg-base-200 p-3 rounded-lg">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="font-semibold">Status:</span>
                        <span
                          className={`badge badge-sm ${
                            selectedTask.status === "completed"
                              ? "badge-success"
                              : selectedTask.status === "failed"
                                ? "badge-error"
                                : "badge-warning"
                          }`}
                        >
                          {selectedTask.status}
                        </span>
                      </div>
                      {selectedTask.end_at && (
                        <div className="flex items-center gap-2">
                          <span className="font-semibold">Calibrated At:</span>
                          <span>
                            {new Date(selectedTask.end_at).toLocaleString(
                              "ja-JP",
                              {
                                timeZone: "Asia/Tokyo",
                              },
                            )}
                          </span>
                        </div>
                      )}
                      {selectedTask.task_id && (
                        <div className="flex items-center gap-2 mt-1">
                          <span className="font-semibold">Task ID:</span>
                          <span className="font-mono truncate">
                            {selectedTask.task_id}
                          </span>
                        </div>
                      )}
                    </div>

                    {/* Input Parameters */}
                    {selectedTask.input_parameters &&
                      Object.keys(selectedTask.input_parameters).length > 0 && (
                        <div className="text-xs bg-base-200 p-3 rounded-lg">
                          <h5 className="font-semibold mb-2">
                            Input Parameters
                          </h5>
                          <div className="space-y-1">
                            {Object.entries(selectedTask.input_parameters)
                              .sort(([a], [b]) => a.localeCompare(b))
                              .map(([key, value]) => {
                                const paramValue: ParameterValue =
                                  typeof value === "object" &&
                                  value !== null &&
                                  "value" in value
                                    ? (value as ParameterValue)
                                    : { value };
                                return (
                                  <div
                                    key={key}
                                    className="flex justify-between"
                                  >
                                    <span className="font-medium">{key}:</span>
                                    <span>
                                      {typeof paramValue.value === "number"
                                        ? paramValue.value.toFixed(4)
                                        : String(paramValue.value)}
                                      {paramValue.unit
                                        ? ` ${paramValue.unit}`
                                        : ""}
                                    </span>
                                  </div>
                                );
                              })}
                          </div>
                        </div>
                      )}

                    {/* Output Parameters */}
                    {selectedTask.output_parameters &&
                      Object.keys(selectedTask.output_parameters).length >
                        0 && (
                        <div className="text-xs bg-base-200 p-3 rounded-lg">
                          <h5 className="font-semibold mb-2">
                            Output Parameters
                          </h5>
                          <div className="space-y-1">
                            {Object.entries(selectedTask.output_parameters)
                              .sort(([a], [b]) => a.localeCompare(b))
                              .map(([key, value]) => {
                                const paramValue: ParameterValue =
                                  typeof value === "object" &&
                                  value !== null &&
                                  "value" in value
                                    ? (value as ParameterValue)
                                    : { value };
                                return (
                                  <div
                                    key={key}
                                    className="flex justify-between"
                                  >
                                    <span className="font-medium">{key}:</span>
                                    <span>
                                      {typeof paramValue.value === "number"
                                        ? paramValue.value.toFixed(4)
                                        : String(paramValue.value)}
                                      {paramValue.unit
                                        ? ` ${paramValue.unit}`
                                        : ""}
                                    </span>
                                  </div>
                                );
                              })}
                          </div>
                        </div>
                      )}

                    {/* Message */}
                    {selectedTask.message && (
                      <div className="text-xs bg-base-200 p-3 rounded-lg">
                        <h5 className="font-semibold mb-1">Message</h5>
                        <p>{selectedTask.message}</p>
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>

            {/* History List - shown second on mobile (bottom), first on desktop (left) */}
            <div className="order-2 lg:order-1 lg:w-1/3 flex flex-col min-h-0">
              <h4 className="text-sm sm:text-md font-bold mb-2 sm:mb-3 flex-shrink-0">
                History
              </h4>
              <div className="flex-1 overflow-y-auto min-h-0 max-h-[150px] sm:max-h-none">
                {/* Mobile: horizontal scroll list */}
                <div className="flex gap-2 overflow-x-auto pb-2 sm:hidden">
                  {historyArray.map((item, idx) => (
                    <button
                      key={item.key}
                      onClick={() => handleSelectIndex(idx)}
                      className={`flex-shrink-0 text-left p-2 rounded-lg transition-all min-w-[90px] ${
                        idx === selectedIndex
                          ? "bg-primary text-primary-content"
                          : "bg-base-200 hover:bg-base-300"
                      }`}
                    >
                      <div className="font-bold text-xs">
                        {item.task.status === "completed" ? (
                          <span
                            className={
                              idx === selectedIndex ? "" : "text-success"
                            }
                          >
                            OK
                          </span>
                        ) : item.task.status === "failed" ? (
                          <span
                            className={
                              idx === selectedIndex ? "" : "text-error"
                            }
                          >
                            Fail
                          </span>
                        ) : (
                          <span
                            className={
                              idx === selectedIndex ? "" : "text-warning"
                            }
                          >
                            {item.task.status}
                          </span>
                        )}
                      </div>
                      <div className="text-[0.65rem] opacity-70">
                        {item.task.end_at
                          ? new Date(item.task.end_at).toLocaleString("ja-JP", {
                              timeZone: "Asia/Tokyo",
                              month: "numeric",
                              day: "numeric",
                              hour: "2-digit",
                              minute: "2-digit",
                            })
                          : "N/A"}
                      </div>
                      {idx === 0 && (
                        <span className="badge badge-xs badge-success mt-0.5">
                          Latest
                        </span>
                      )}
                    </button>
                  ))}
                </div>
                {/* Mobile: selected item details below cards */}
                {selectedItem && (
                  <div className="sm:hidden mt-2 p-2 bg-base-200 rounded-lg text-xs space-y-1">
                    <div className="flex justify-between">
                      <span className="opacity-70">Task ID:</span>
                      <span className="font-mono truncate max-w-[180px]">
                        {selectedItem.task.task_id}
                      </span>
                    </div>
                    {selectedItem.task.message && (
                      <div className="flex justify-between">
                        <span className="opacity-70">Message:</span>
                        <span className="truncate max-w-[180px]">
                          {selectedItem.task.message}
                        </span>
                      </div>
                    )}
                  </div>
                )}
                {/* Desktop: vertical list */}
                <div className="hidden sm:flex flex-col gap-2">
                  {historyArray.map((item, idx) => (
                    <button
                      key={item.key}
                      onClick={() => handleSelectIndex(idx)}
                      className={`w-full text-left p-3 rounded-lg transition-all ${
                        idx === selectedIndex
                          ? "bg-primary text-primary-content"
                          : "bg-base-200 hover:bg-base-300"
                      }`}
                    >
                      <div className="flex justify-between items-start">
                        <div>
                          <div className="font-bold text-sm">
                            {item.task.status === "completed" ? (
                              <span
                                className={
                                  idx === selectedIndex ? "" : "text-success"
                                }
                              >
                                Completed
                              </span>
                            ) : item.task.status === "failed" ? (
                              <span
                                className={
                                  idx === selectedIndex ? "" : "text-error"
                                }
                              >
                                Failed
                              </span>
                            ) : (
                              <span
                                className={
                                  idx === selectedIndex ? "" : "text-warning"
                                }
                              >
                                {item.task.status}
                              </span>
                            )}
                          </div>
                          <div className="text-xs opacity-70 mt-1">
                            {item.task.end_at
                              ? new Date(item.task.end_at).toLocaleString(
                                  "ja-JP",
                                  {
                                    timeZone: "Asia/Tokyo",
                                    month: "short",
                                    day: "numeric",
                                    hour: "2-digit",
                                    minute: "2-digit",
                                  },
                                )
                              : "N/A"}
                          </div>
                          {idx === 0 && (
                            <span className="badge badge-sm badge-success mt-1">
                              Latest
                            </span>
                          )}
                        </div>
                        <div className="text-xs opacity-60">#{idx + 1}</div>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
      <form method="dialog" className="modal-backdrop">
        <button onClick={onClose}>close</button>
      </form>
    </dialog>
  );
}
