"use client";

import { useFetchAllTasks } from "@/client/task/task";
import { TaskResponse } from "@/schemas";
import { useState } from "react";
import { BsGrid, BsListUl, BsArrowRight } from "react-icons/bs";

type ViewMode = "grid" | "list";

export default function TasksPage() {
  const { data: tasksData } = useFetchAllTasks();
  const [viewMode, setViewMode] = useState<ViewMode>("grid");

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
    <div className="card bg-base-100 shadow-lg hover:shadow-xl transition-all duration-300 group h-full">
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
        <div className="card-actions justify-end mt-auto pt-4">
          <button className="btn btn-ghost btn-sm group-hover:text-primary transition-colors">
            View Details <BsArrowRight className="ml-2" />
          </button>
        </div>
      </div>
    </div>
  );

  const TaskRow = ({ task }: { task: TaskResponse }) => (
    <div className="bg-base-100 p-4 rounded-lg shadow hover:shadow-md transition-all duration-300 group">
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
        <button className="btn btn-ghost btn-sm group-hover:text-primary transition-colors shrink-0">
          View Details <BsArrowRight className="ml-2" />
        </button>
      </div>
    </div>
  );

  return (
    <div className="w-full px-6 py-6" style={{ width: "calc(100vw - 20rem)" }}>
      <div className="space-y-6">
        <div className="flex justify-between items-center">
          <h1 className="text-2xl font-bold">Task Definitions</h1>
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
