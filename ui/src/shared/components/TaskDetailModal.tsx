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
  chipId: string;
  selectedDate: string;
  onNavigatePrevious: () => void;
  onNavigateNext: () => void;
  canNavigatePrevious: boolean;
  canNavigateNext: boolean;
  formatDate: (date: string) => string;
  initialSubIndex?: number;
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
}: TaskDetailModalProps) {
  const router = useRouter();
  const [viewMode, setViewMode] = useState<"static" | "interactive">("static");
  const [subIndex, setSubIndex] = useState(initialSubIndex);

  if (!isOpen || !task) return null;

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

  return (
    <dialog className="modal modal-open">
      <div className="modal-box max-w-6xl p-6 rounded-2xl shadow-xl bg-base-100">
        <div className="flex justify-between items-center mb-4">
          <h3 className="font-bold text-lg">Result for QID {qid}</h3>
          <div className="flex items-center gap-2">
            <button
              onClick={onNavigatePrevious}
              disabled={!canNavigatePrevious}
              className="btn btn-sm btn-ghost"
              title="Previous Day"
            >
              ←
            </button>
            <span className="text-sm text-base-content/70 px-2">
              {formatDate(selectedDate)}
            </span>
            <button
              onClick={onNavigateNext}
              disabled={!canNavigateNext}
              className="btn btn-sm btn-ghost"
              title="Next Day"
            >
              →
            </button>
            <button
              onClick={() => router.push(`/chip/${chipId}/qubit/${qid}`)}
              className="btn btn-sm btn-primary"
              title="Detailed Analysis"
            >
              Detail View
            </button>
            <button
              onClick={onClose}
              className="btn btn-sm btn-circle btn-ghost"
            >
              ✕
            </button>
          </div>
        </div>

        {viewMode === "static" && (
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
                        (subIndex - 1 + figures.length) % figures.length,
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
                    onClick={() => setSubIndex((subIndex + 1) % figures.length)}
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
                          <div key={key} className="flex justify-between">
                            <span className="font-medium">{key}:</span>
                            <span>
                              {typeof paramValue.value === "number"
                                ? paramValue.value.toFixed(4)
                                : String(paramValue.value)}
                              {paramValue.unit ? ` ${paramValue.unit}` : ""}
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
