"use client";

import React, { useState } from "react";

import type { Task } from "@/schemas";

import { TaskFigure } from "@/components/charts/TaskFigure";
import { TaskDetailModal } from "@/components/features/chip/modals/TaskDetailModal";

interface TaskWithId extends Task {
  taskId: string;
}

interface TaskGridViewProps {
  tasks: TaskWithId[];
  qubitId?: string;
  emptyMessage?: string;
}

export function TaskGridView({
  tasks,
  qubitId = "",
  emptyMessage = "No tasks available",
}: TaskGridViewProps) {
  const [modalTaskId, setModalTaskId] = useState<string | null>(null);

  const modalTask = tasks.find((t) => t.taskId === modalTaskId);

  const getStatusBadge = (status?: string) => {
    switch (status) {
      case "completed":
        return <span className="badge badge-success badge-sm">Completed</span>;
      case "failed":
        return <span className="badge badge-error badge-sm">Failed</span>;
      case "running":
        return <span className="badge badge-info badge-sm">Running</span>;
      case "scheduled":
        return <span className="badge badge-warning badge-sm">Scheduled</span>;
      default:
        return <span className="badge badge-warning badge-sm">Unknown</span>;
    }
  };

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

  if (tasks.length === 0) {
    return (
      <div className="flex justify-center items-center h-96">
        <div className="text-center text-base-content/60">
          <div className="text-4xl mb-2">📭</div>
          <div className="text-sm">{emptyMessage}</div>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        {tasks.map((task) => {
          const figurePath =
            task.figure_path && task.figure_path.length > 0
              ? Array.isArray(task.figure_path)
                ? task.figure_path[0]
                : task.figure_path
              : null;

          return (
            <div
              key={task.taskId}
              className="card bg-base-100 shadow-lg hover:shadow-xl transition-all cursor-pointer group"
              onClick={() => setModalTaskId(task.taskId)}
            >
              <div className="card-body p-4">
                {/* Status Badge */}
                <div className="flex items-center justify-between mb-2">
                  <div className="text-xs font-mono text-base-content/60 truncate">
                    {task.qid ? `Q${task.qid}` : task.taskId?.slice(-8)}
                  </div>
                  {getStatusBadge(task.status)}
                </div>

                {/* Figure */}
                {figurePath ? (
                  <div className="bg-base-200 rounded-lg p-2 aspect-square flex items-center justify-center mb-3">
                    <TaskFigure
                      path={figurePath}
                      qid={task.qid || qubitId}
                      className="w-full h-full object-contain"
                    />
                  </div>
                ) : (
                  <div className="bg-base-200 rounded-lg p-2 aspect-square flex items-center justify-center mb-3">
                    <div className="text-center text-base-content/40">
                      <div className="text-4xl mb-2">📊</div>
                      <div className="text-xs">No Figure</div>
                    </div>
                  </div>
                )}

                {/* Task Info */}
                <div className="space-y-2">
                  <div
                    className="font-semibold text-sm truncate"
                    title={task.name}
                  >
                    {task.name}
                  </div>

                  <div className="text-sm">{formatDateTime(task.start_at)}</div>

                  {task.elapsed_time && (
                    <div className="text-xs text-base-content/60">
                      ⏱ {task.elapsed_time}
                    </div>
                  )}

                  {task.message && (
                    <div className="text-xs text-base-content/70 line-clamp-2">
                      {task.message}
                    </div>
                  )}

                  {task.output_parameters && (
                    <div className="text-xs text-base-content/60">
                      {Object.keys(task.output_parameters).length} parameters
                    </div>
                  )}
                </div>

                {/* Hover indicator */}
                <div className="mt-2 text-center">
                  <span className="text-xs badge badge-primary opacity-0 group-hover:opacity-100 transition-opacity">
                    Click to view details
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Task Detail Modal */}
      <TaskDetailModal
        isOpen={!!modalTask}
        task={modalTask || null}
        qid={modalTask?.qid || qubitId}
        onClose={() => setModalTaskId(null)}
        taskId={modalTask?.taskId}
        taskName={modalTask?.name}
        variant="detailed"
      />
    </>
  );
}
