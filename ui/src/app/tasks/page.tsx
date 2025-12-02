"use client";

import { useState } from "react";

import { BsGrid, BsListUl, BsX } from "react-icons/bs";
import {
  BsInfoCircle,
  BsArrowDownSquare,
  BsArrowUpSquare,
} from "react-icons/bs";

import type { TaskResponse } from "@/schemas";

import { BackendSelector } from "@/app/components/BackendSelector";
import { useListTasks } from "@/client/task/task";

type ViewMode = "grid" | "list";

interface Parameter {
  unit?: string;
  value_type?: string;
  value?: any;
  description?: string;
}

interface TaskDetailModalProps {
  task: TaskResponse | null;
  onClose: () => void;
}

const TaskDetailModal = ({ task, onClose }: TaskDetailModalProps) => {
  if (!task) return null;

  const renderParameterValue = (value: any) => {
    if (Array.isArray(value)) {
      return `[${value.join(", ")}]`;
    }
    return String(value);
  };

  const renderParameters = (parameters: Record<string, Parameter>) => {
    return Object.entries(parameters).map(([name, param]) => (
      <div
        key={name}
        className="mb-6 last:mb-0 bg-base-100/40 rounded-lg p-4 hover:bg-base-100/60 transition-colors"
      >
        <div className="flex items-start gap-3">
          <h4 className="font-semibold text-base flex-1">{name}</h4>
          {param.unit && (
            <span className="badge badge-neutral badge-sm font-mono">
              {param.unit}
            </span>
          )}
        </div>
        <div className="mt-3 space-y-3">
          {param.description && (
            <p className="text-sm text-base-content/70 leading-relaxed">
              {param.description}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <span className="font-mono text-xs bg-base-300/50 px-3 py-1.5 rounded-full">
              {param.value_type}
            </span>
            {param.value !== null && (
              <span className="font-mono text-xs bg-primary/10 text-primary px-3 py-1.5 rounded-full">
                {renderParameterValue(param.value)}
              </span>
            )}
          </div>
        </div>
      </div>
    ));
  };

  return (
    <div
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="bg-base-100 rounded-xl w-full max-w-3xl max-h-[90vh] overflow-hidden flex flex-col shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-6 py-4 border-b border-base-300 flex items-center justify-between bg-base-100/80 backdrop-blur supports-[backdrop-filter]:bg-base-100/60">
          <div className="flex items-center gap-3">
            <h2 className="text-2xl font-bold">{task.name}</h2>
            <div className="badge badge-primary badge-outline font-medium">
              {task.task_type}
            </div>
          </div>
          <button
            onClick={onClose}
            className="btn btn-ghost btn-sm btn-square hover:rotate-90 transition-transform"
          >
            <BsX className="text-xl" />
          </button>
        </div>
        <div className="p-8 overflow-y-auto">
          {task.description && (
            <div className="mb-8">
              <h3 className="text-lg font-semibold mb-3 flex items-center gap-2 text-base-content/80">
                <BsInfoCircle className="text-lg" />
                Description
              </h3>
              <p className="text-base-content/70 leading-relaxed">
                {task.description}
              </p>
            </div>
          )}

          {Object.keys(task.input_parameters || {}).length > 0 && (
            <div className="mb-8">
              <h3 className="text-lg font-semibold mb-3 flex items-center gap-2 text-base-content/80">
                <BsArrowDownSquare className="text-lg" />
                Input Parameters
              </h3>
              <div className="bg-base-200/50 rounded-xl p-6 border border-base-300">
                {renderParameters(task.input_parameters)}
              </div>
            </div>
          )}

          {Object.keys(task.output_parameters || {}).length > 0 && (
            <div className="mb-8">
              <h3 className="text-lg font-semibold mb-3 flex items-center gap-2 text-base-content/80">
                <BsArrowUpSquare className="text-lg" />
                Output Parameters
              </h3>
              <div className="bg-base-200/50 rounded-xl p-6 border border-base-300">
                {renderParameters(task.output_parameters)}
              </div>
            </div>
          )}
          {task.backend && (
            <div>
              <h3 className="text-lg font-semibold mb-3 flex items-center gap-2 text-base-content/80">
                <BsInfoCircle className="text-lg" />
                Backend Information
              </h3>
              <div className="bg-base-200/50 rounded-xl p-6 border border-base-300">
                <div className="bg-base-100/40 rounded-lg p-4 font-mono text-base">
                  {task.backend}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default function TasksPage() {
  const [selectedBackend, setSelectedBackend] = useState<string | null>(null);
  const { data: tasksData } = useListTasks({
    backend: selectedBackend,
  });
  const [viewMode, setViewMode] = useState<ViewMode>("grid");
  const [selectedTask, setSelectedTask] = useState<TaskResponse | null>(null);

  // Group tasks by type
  const groupedTasks =
    tasksData?.data?.tasks?.reduce(
      (acc: { [key: string]: TaskResponse[] }, task: TaskResponse) => {
        const type = task.task_type || "other";
        if (!acc[type]) {
          acc[type] = [];
        }
        acc[type].push(task);
        return acc;
      },
      {},
    ) || {};

  const TaskCard = ({ task }: { task: TaskResponse }) => (
    <div
      className="card bg-base-100 shadow-lg hover:shadow-xl transition-all duration-300 group h-full cursor-pointer hover:scale-[1.02]"
      onClick={() => setSelectedTask(task)}
    >
      <div className="card-body flex flex-col p-4">
        <div className="space-y-2">
          <div className="flex flex-wrap gap-2 items-start">
            <h3 className="card-title text-lg group-hover:text-primary transition-colors break-all flex-1 min-w-0">
              {task.name}
            </h3>
            <div className="badge badge-primary badge-outline shrink-0 max-w-full overflow-hidden text-ellipsis">
              {task.task_type}
            </div>
          </div>
          {task.description && (
            <p className="text-base-content/70 mt-2 line-clamp-3">
              {task.description}
            </p>
          )}
        </div>
      </div>
    </div>
  );

  const TaskRow = ({ task }: { task: TaskResponse }) => (
    <div
      className="bg-base-100 p-4 rounded-lg shadow hover:shadow-md transition-all duration-300 group cursor-pointer hover:scale-[1.01]"
      onClick={() => setSelectedTask(task)}
    >
      <div className="flex items-center justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-lg font-medium group-hover:text-primary transition-colors break-all">
              {task.name}
            </h3>
            <div className="badge badge-primary badge-outline shrink-0 max-w-[200px] overflow-hidden text-ellipsis">
              {task.task_type}
            </div>
          </div>
          {task.description && (
            <p className="text-base-content/70 mt-1 line-clamp-2 break-words">
              {task.description}
            </p>
          )}
        </div>
      </div>
    </div>
  );

  return (
    <div className="w-full px-6 py-6">
      <div className="space-y-6">
        <div className="flex justify-between items-center gap-4">
          <h1 className="text-2xl font-bold">Task Definitions</h1>
          <div className="flex items-center gap-4">
            <BackendSelector
              selectedBackend={selectedBackend}
              onBackendSelect={setSelectedBackend}
            />
            <div className="join">
              <button
                className={`join-item btn btn-sm ${
                  viewMode === "grid" ? "btn-active" : ""
                }`}
                onClick={() => setViewMode("grid")}
              >
                <BsGrid className="text-lg" />
              </button>
              <button
                className={`join-item btn btn-sm ${
                  viewMode === "list" ? "btn-active" : ""
                }`}
                onClick={() => setViewMode("list")}
              >
                <BsListUl className="text-lg" />
              </button>
            </div>
          </div>
        </div>

        {Object.entries(groupedTasks).map(([type, tasks]) => (
          <div key={type} className="space-y-4">
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-semibold capitalize">{type}</h2>
              <div className="badge badge-neutral">{tasks.length}</div>
            </div>
            <div
              className={
                viewMode === "grid"
                  ? "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"
                  : "space-y-4"
              }
            >
              {tasks.map((task) =>
                viewMode === "grid" ? (
                  <TaskCard key={task.name} task={task} />
                ) : (
                  <TaskRow key={task.name} task={task} />
                ),
              )}
            </div>
          </div>
        ))}

        {selectedTask && (
          <TaskDetailModal
            task={selectedTask}
            onClose={() => setSelectedTask(null)}
          />
        )}

        {!tasksData?.data?.tasks?.length && (
          <div className="alert alert-info">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              className="stroke-current shrink-0 w-6 h-6"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            <span>No tasks found</span>
          </div>
        )}
      </div>
    </div>
  );
}
