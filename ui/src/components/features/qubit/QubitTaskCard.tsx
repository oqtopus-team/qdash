"use client";

import type { Task, TaskInfo } from "@/schemas";

import { TaskFigure } from "@/components/charts/TaskFigure";
import { FluentEmoji } from "@/components/ui/FluentEmoji";
import { useQubitTaskResults } from "@/hooks/useQubitTaskResults";

interface QubitTaskCardProps {
  task: TaskInfo;
  chipId: string;
  qubitId: string;
  selectedDate: string;
  onViewDetails: (taskName: string) => void;
}

export function QubitTaskCard({
  task,
  chipId,
  qubitId,
  selectedDate,
  onViewDetails,
}: QubitTaskCardProps) {
  const { data, isLoading } = useQubitTaskResults({
    chipId,
    task: task.name,
    selectedDate,
  });

  const taskData: Task | null = data?.data?.result?.[qubitId] || null;

  if (isLoading) {
    return (
      <div className="card bg-base-100 shadow-xl">
        <div className="card-body p-4">
          <h3 className="card-title text-lg">{task.name}</h3>
          <div className="flex justify-center py-8">
            <span className="loading loading-spinner loading-md" />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="card bg-base-100 shadow-xl hover:shadow-2xl transition-shadow">
      <div className="card-body p-4">
        <h3 className="card-title text-lg flex items-center justify-between">
          {task.name.replace("Check", "")}
          <div
            className={`badge ${
              taskData?.status === "completed"
                ? "badge-success"
                : taskData?.status === "failed"
                  ? "badge-error"
                  : "badge-ghost"
            }`}
          >
            {taskData?.status || "No Data"}
          </div>
        </h3>

        {taskData ? (
          <div className="space-y-3">
            {taskData.figure_path && (
              <div className="relative h-32 bg-base-200 rounded-lg overflow-hidden">
                <TaskFigure
                  path={
                    Array.isArray(taskData.figure_path)
                      ? taskData.figure_path[0]
                      : taskData.figure_path
                  }
                  qid={qubitId}
                  className="w-full h-full object-contain"
                />
              </div>
            )}

            {taskData.output_parameters && (
              <div className="bg-base-200 p-2 rounded">
                {Object.entries(taskData.output_parameters)
                  .slice(0, 3)
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
                      <div key={key} className="text-xs flex justify-between">
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
                {Object.keys(taskData.output_parameters).length > 3 && (
                  <div className="text-xs text-center text-base-content/60 mt-1">
                    +{Object.keys(taskData.output_parameters).length - 3}{" "}
                    more...
                  </div>
                )}
              </div>
            )}

            <div className="card-actions justify-end">
              <button
                className="btn btn-sm btn-primary"
                onClick={() => onViewDetails(task.name)}
              >
                View Details
              </button>
            </div>
          </div>
        ) : (
          <div className="text-center text-base-content/60 py-8">
            <FluentEmoji name="empty" size={48} className="mb-2 mx-auto" />
            <div className="text-sm">No execution results</div>
          </div>
        )}
      </div>
    </div>
  );
}
