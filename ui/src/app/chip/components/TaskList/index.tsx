"use client";

import { ServerRoutersChipTask } from "@/schemas";
import { useState } from "react";

interface TaskListProps {
  taskGroups: {
    [key: string]: { [key: string]: ServerRoutersChipTask };
  };
  qids: string[];
  muxId: string;
}

interface SelectedTaskInfo {
  path: string;
  qid: string;
  task: ServerRoutersChipTask;
}

export function TaskList({ taskGroups, qids }: TaskListProps) {
  const [selectedTaskInfo, setSelectedTaskInfo] =
    useState<SelectedTaskInfo | null>(null);

  // Get figure path from task
  const getFigurePath = (task: ServerRoutersChipTask): string | null => {
    if (!task.figure_path) return null;
    if (Array.isArray(task.figure_path)) {
      return task.figure_path[0] || null;
    }
    return task.figure_path;
  };

  return (
    <div className="space-y-6">
      {Object.entries(taskGroups).map(([taskName, tasks]) => (
        <div key={taskName} className="space-y-4">
          <h3 className="text-lg font-medium">{taskName}</h3>
          <div className="grid grid-cols-2 gap-4">
            {qids.map((qid) => {
              const task = tasks[qid];
              if (!task) return null;

              const figurePath = getFigurePath(task);

              return (
                <div
                  key={qid}
                  className="card bg-base-200 shadow-sm"
                  onClick={() => {
                    if (figurePath) {
                      setSelectedTaskInfo({
                        path: figurePath,
                        qid,
                        task,
                      });
                    }
                  }}
                >
                  <div className="card-body p-4">
                    <div className="flex justify-between items-start mb-2">
                      <div className="font-medium">QID {qid}</div>
                      <div
                        className={`w-2 h-2 rounded-full ${
                          task.status === "completed"
                            ? "bg-success"
                            : task.status === "failed"
                              ? "bg-error"
                              : "bg-warning"
                        }`}
                      />
                    </div>
                    {task.output_parameters && (
                      <div className="text-sm space-y-1">
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
                                <span className="text-base-content/70">
                                  {key}:
                                </span>
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
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ))}

      {/* Task Result Modal */}
      {selectedTaskInfo && (
        <dialog className="modal modal-open">
          <div className="modal-box max-w-4xl bg-base-100">
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-bold text-lg">
                Result for QID {selectedTaskInfo.qid}
              </h3>
              <button
                onClick={() => setSelectedTaskInfo(null)}
                className="btn btn-sm btn-circle btn-ghost"
              >
                ✕
              </button>
            </div>
            <div className="grid grid-cols-2 gap-8">
              <div className="aspect-square bg-base-200/50 rounded-xl p-4">
                <img
                  src={`http://localhost:5715/executions/figure?path=${encodeURIComponent(
                    selectedTaskInfo.path,
                  )}`}
                  alt={`Result for QID ${selectedTaskInfo.qid}`}
                  className="w-full h-full object-contain"
                />
              </div>
              <div className="space-y-6">
                <div className="card bg-base-200 p-4 rounded-xl">
                  <h4 className="font-medium mb-2">Status</h4>
                  <div
                    className={`badge ${
                      selectedTaskInfo.task.status === "completed"
                        ? "badge-success"
                        : selectedTaskInfo.task.status === "failed"
                          ? "badge-error"
                          : "badge-warning"
                    }`}
                  >
                    {selectedTaskInfo.task.status}
                  </div>
                </div>
                {selectedTaskInfo.task.output_parameters && (
                  <div className="card bg-base-200 p-4 rounded-xl">
                    <h4 className="font-medium mb-2">Parameters</h4>
                    <div className="space-y-2">
                      {Object.entries(
                        selectedTaskInfo.task.output_parameters,
                      ).map(([key, value]) => {
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
                      })}
                    </div>
                  </div>
                )}
                {selectedTaskInfo.task.message && (
                  <div className="card bg-base-200 p-4 rounded-xl">
                    <h4 className="font-medium mb-2">Message</h4>
                    <p className="text-sm">{selectedTaskInfo.task.message}</p>
                  </div>
                )}
              </div>
            </div>
          </div>
          <form method="dialog" className="modal-backdrop">
            <button onClick={() => setSelectedTaskInfo(null)}>close</button>
          </form>
        </dialog>
      )}
    </div>
  );
}
