"use client";

import { useState } from "react";
import { ServerRoutersChipTask } from "@/schemas";

interface TaskResultGridProps {
  taskGroups: {
    [key: string]: { [key: string]: ServerRoutersChipTask };
  };
  qids: string[];
  muxId: string;
}

interface ParameterValue {
  value: number | string;
  unit?: string;
  calibrated_at?: string;
}

type ViewMode = "image" | "params";
interface TaskCardState {
  [key: string]: ViewMode;
}

export function TaskResultGrid({
  taskGroups,
  qids,
  muxId,
}: TaskResultGridProps) {
  const [viewModes, setViewModes] = useState<TaskCardState>({});

  // Format relative time
  const formatRelativeTime = (date: Date): string => {
    const now = new Date();
    const diffInSeconds = Math.floor((now.getTime() - date.getTime()) / 1000);

    if (diffInSeconds < 60) return "just now";
    if (diffInSeconds < 3600) return `${Math.floor(diffInSeconds / 60)}m ago`;
    if (diffInSeconds < 86400)
      return `${Math.floor(diffInSeconds / 3600)}h ago`;
    return date.toLocaleString();
  };

  // Toggle view mode for a task
  const toggleViewMode = (taskId: string) => {
    setViewModes((prev) => ({
      ...prev,
      [taskId]: prev[taskId] === "image" ? "params" : "image",
    }));
  };

  // Get view mode for a task
  const getViewMode = (taskId: string): ViewMode => {
    return viewModes[taskId] || "image";
  };

  return (
    <div className="space-y-6">
      {Object.entries(taskGroups).map(([taskName, qidResults]) => (
        <div
          key={taskName}
          className="border-t pt-4 first:border-t-0 first:pt-0"
        >
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-lg font-medium">{taskName}</h3>
            <div className="badge badge-ghost">
              {Object.keys(qidResults).length} Results
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {qids.map((qid) => {
              const task = qidResults[qid];
              if (!task) return null;

              const taskId = `${muxId}-${qid}-${taskName}`;
              const viewMode = getViewMode(taskId);

              return (
                <div
                  key={qid}
                  className="card bg-base-100 shadow-sm rounded-xl overflow-hidden hover:shadow-md transition-shadow"
                >
                  <div className="card-body p-3">
                    <div className="flex justify-between items-center mb-2">
                      <div className="flex items-center gap-2">
                        <span className="font-medium">QID: {qid}</span>
                        <div
                          className={`badge badge-sm ${
                            task.status === "completed"
                              ? "badge-success"
                              : "badge-error"
                          }`}
                        >
                          {task.status}
                        </div>
                      </div>
                      {task?.output_parameters && (
                        <div className="tabs tabs-boxed rounded-lg">
                          <a
                            className={`tab tab-xs ${
                              viewMode === "image" ? "tab-active" : ""
                            }`}
                            onClick={() => toggleViewMode(taskId)}
                          >
                            Image
                          </a>
                          <a
                            className={`tab tab-xs ${
                              viewMode === "params" ? "tab-active" : ""
                            }`}
                            onClick={() => toggleViewMode(taskId)}
                          >
                            Params
                          </a>
                        </div>
                      )}
                    </div>
                    {task?.end_at && (
                      <div className="text-xs text-base-content/60 mb-2">
                        Updated: {formatRelativeTime(new Date(task.end_at))}
                      </div>
                    )}

                    {viewMode === "image" && task.figure_path && (
                      <div className="relative h-48 rounded-lg overflow-hidden bg-base-200">
                        {Array.isArray(task.figure_path) ? (
                          task.figure_path.map((path, i) => (
                            <img
                              key={i}
                              src={`http://localhost:5715/executions/figure?path=${encodeURIComponent(
                                path,
                              )}`}
                              alt={`Result for QID ${qid}`}
                              className="w-full h-48 object-contain hover:scale-110 transition-transform"
                            />
                          ))
                        ) : (
                          <img
                            src={`http://localhost:5715/executions/figure?path=${encodeURIComponent(
                              task.figure_path,
                            )}`}
                            alt={`Result for QID ${qid}`}
                            className="w-full h-48 object-contain hover:scale-110 transition-transform"
                          />
                        )}
                      </div>
                    )}

                    {viewMode === "params" && task.output_parameters && (
                      <div className="h-48 overflow-y-auto rounded-lg">
                        <table className="table table-xs table-zebra w-full rounded-lg overflow-hidden">
                          <thead className="bg-base-200 sticky top-0">
                            <tr>
                              <th className="rounded-tl-lg">Parameter</th>
                              <th>Value</th>
                              <th className="rounded-tr-lg">Updated</th>
                            </tr>
                          </thead>
                          <tbody className="text-xs">
                            {Object.entries(task.output_parameters).map(
                              ([key, value]) => {
                                const paramValue =
                                  typeof value === "object" &&
                                  value !== null &&
                                  "value" in value
                                    ? (value as ParameterValue)
                                    : ({ value } as ParameterValue);
                                return (
                                  <tr key={key}>
                                    <td className="font-medium py-0.5">
                                      {key}
                                    </td>
                                    <td className="text-right py-0.5">
                                      {typeof paramValue.value === "number"
                                        ? paramValue.value.toFixed(4)
                                        : String(paramValue.value)}
                                      {paramValue.unit
                                        ? ` ${paramValue.unit}`
                                        : ""}
                                    </td>
                                    <td className="text-right py-0.5 text-base-content/60">
                                      {paramValue.calibrated_at
                                        ? new Date(
                                            paramValue.calibrated_at,
                                          ).toLocaleString()
                                        : "-"}
                                    </td>
                                  </tr>
                                );
                              },
                            )}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
