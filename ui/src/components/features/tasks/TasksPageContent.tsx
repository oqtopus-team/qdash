"use client";

import { useEffect, useMemo, useState } from "react";

import { useQuery } from "@tanstack/react-query";
import { Braces, Copy, PanelLeft, Search, X } from "lucide-react";

import type {
  ListTaskFileBackendsResponse,
  ListTaskInfoResponse,
  TaskFileBackend,
  TaskFileSettings,
  TaskInfo,
} from "@/schemas";
import type { AxiosResponse } from "axios";

import {
  getTaskFileSettings,
  listTaskFileBackends,
  listTaskInfo,
} from "@/client/task-file/task-file";
import { EditorPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";
import { useToast } from "@/components/ui/Toast";

import { TaskWorkbench } from "./TaskWorkbench";

export function TasksPageContent() {
  const toast = useToast();
  const [selectedBackend, setSelectedBackend] = useState<string | null>(null);
  const [selectedTask, setSelectedTask] = useState<TaskInfo | null>(null);
  const [isSidebarVisible, setIsSidebarVisible] = useState(true);
  const [taskSearch, setTaskSearch] = useState("");

  const { data: settingsData, isPending: isSettingsPending } = useQuery({
    queryKey: ["taskFileSettings"],
    queryFn: () =>
      getTaskFileSettings().then((response: AxiosResponse<TaskFileSettings>) => response.data),
  });

  const {
    data: backendsData,
    isLoading: isBackendsLoading,
    error: backendsError,
  } = useQuery({
    queryKey: ["taskFileBackends"],
    queryFn: () =>
      listTaskFileBackends().then(
        (response: AxiosResponse<ListTaskFileBackendsResponse>) => response.data,
      ),
  });

  useEffect(() => {
    if (isSettingsPending || !backendsData?.backends.length || selectedBackend) return;
    const configuredBackend = settingsData?.default_backend;
    const backend = backendsData.backends.find((item) => item.name === configuredBackend);
    setSelectedBackend(backend?.name ?? backendsData.backends[0].name);
  }, [backendsData?.backends, isSettingsPending, selectedBackend, settingsData?.default_backend]);

  const { data: taskListData, isLoading: isTaskListLoading } = useQuery({
    queryKey: ["taskList", selectedBackend, settingsData?.sort_order],
    queryFn: () =>
      listTaskInfo({
        backend: selectedBackend!,
        sort_order: settingsData?.sort_order ?? undefined,
      }).then((response: AxiosResponse<ListTaskInfoResponse>) => response.data),
    enabled: Boolean(selectedBackend),
  });

  useEffect(() => {
    if (!taskListData?.tasks.length) return;

    if (!selectedTask) {
      setSelectedTask(taskListData.tasks.find((task) => task.enabled) ?? taskListData.tasks[0]);
      return;
    }

    // Keep the selected task aligned with refetched metadata. Holding the old
    // object here would leave parameter declarations stale until a full reload.
    const refreshedTask = taskListData.tasks.find(
      (task) => task.name === selectedTask.name && task.file_path === selectedTask.file_path,
    );
    if (refreshedTask && refreshedTask !== selectedTask) {
      setSelectedTask(refreshedTask);
    }
  }, [selectedTask, taskListData?.tasks]);

  const filteredTasks = useMemo(() => {
    const tasks = taskListData?.tasks ?? [];
    const query = taskSearch.trim().toLowerCase();
    if (!query) return tasks;
    return tasks.filter(
      (task) =>
        task.name.toLowerCase().includes(query) ||
        task.task_type?.toLowerCase().includes(query) ||
        task.file_path.toLowerCase().includes(query),
    );
  }, [taskListData?.tasks, taskSearch]);

  const groupedTasks = useMemo(
    () =>
      filteredTasks.reduce<Record<string, TaskInfo[]>>((groups, task) => {
        const type = task.task_type || "other";
        (groups[type] ??= []).push(task);
        return groups;
      }, {}),
    [filteredTasks],
  );

  const copyTaskName = async (taskName: string) => {
    try {
      await navigator.clipboard.writeText(taskName);
      toast.success(`Copied: ${taskName}`);
    } catch {
      toast.error("Failed to copy to clipboard");
    }
  };

  if (isBackendsLoading) return <EditorPageSkeleton />;

  if (backendsError) {
    return (
      <div className="container mx-auto p-6">
        <div className="alert alert-error">
          <span>Failed to load backends: {(backendsError as Error).message}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100dvh-4rem)] flex-col bg-base-300">
      <header className="flex items-center justify-between gap-3 border-b border-base-300 bg-base-200 px-4 py-2">
        <div className="min-w-0">
          <h1 className="text-sm font-medium">Tasks</h1>
          <p className="truncate text-xs text-base-content/50">
            Configure, run, and inspect calibration tasks
          </p>
        </div>
        <select
          value={selectedBackend ?? ""}
          onChange={(event) => {
            setSelectedBackend(event.target.value);
            setSelectedTask(null);
          }}
          className="select select-sm select-bordered"
          aria-label="Task backend"
        >
          {backendsData?.backends.map((backend: TaskFileBackend) => (
            <option key={backend.name} value={backend.name}>
              {backend.name}
            </option>
          ))}
        </select>
      </header>

      <main className="flex min-h-0 flex-1 overflow-hidden">
        <aside className="flex shrink-0 border-r border-base-300 bg-base-100">
          <div
            className={`${isSidebarVisible ? "w-64" : "w-0"} flex flex-col overflow-hidden transition-all duration-200`}
          >
            <div className="border-b border-base-300 p-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <h2 className="text-xs font-bold tracking-wider text-base-content/60">TASKS</h2>
                <span className="text-xs text-base-content/45">
                  {filteredTasks.length}/{taskListData?.tasks.length ?? 0}
                </span>
              </div>
              <label className="input input-sm input-bordered flex w-full items-center gap-2 bg-base-100">
                <Search className="h-3.5 w-3.5 shrink-0 text-base-content/40" />
                <input
                  value={taskSearch}
                  onChange={(event) => setTaskSearch(event.target.value)}
                  className="min-w-0 grow text-sm"
                  placeholder="Search tasks"
                  aria-label="Search tasks"
                />
                {taskSearch && (
                  <button
                    type="button"
                    className="btn btn-ghost btn-xs btn-square"
                    onClick={() => setTaskSearch("")}
                    aria-label="Clear task search"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                )}
              </label>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto py-2">
              {isTaskListLoading ? (
                <div className="flex justify-center py-4">
                  <span className="loading loading-spinner loading-sm" />
                </div>
              ) : filteredTasks.length === 0 ? (
                <div className="px-4 py-8 text-center text-sm text-base-content/50">
                  No tasks found
                </div>
              ) : (
                <div className="space-y-2">
                  {Object.entries(groupedTasks).map(([taskType, tasks]) => (
                    <details key={taskType} className="group" open>
                      <summary className="flex cursor-pointer select-none items-center px-3 py-1 text-xs font-semibold uppercase tracking-wider text-base-content/60 hover:bg-base-200">
                        <span className="mr-1 transition-transform group-open:rotate-90">▸</span>
                        {taskType}
                        <span className="ml-2 text-base-content/40">({tasks.length})</span>
                      </summary>
                      <div className="space-y-0.5">
                        {tasks.map((task) => (
                          <div
                            key={`${task.file_path}-${task.name}`}
                            className="group/item flex px-2"
                          >
                            <button
                              type="button"
                              className={`flex min-w-0 flex-1 items-center gap-2 rounded px-2 py-1.5 text-left hover:bg-base-200 ${selectedTask?.name === task.name ? "bg-base-200" : ""}`}
                              onClick={() => setSelectedTask(task)}
                            >
                              <Braces className="shrink-0 text-purple-400" size={14} />
                              <span className="truncate text-sm text-base-content/80">
                                {task.name}
                              </span>
                            </button>
                            <button
                              type="button"
                              onClick={() => copyTaskName(task.name)}
                              className="rounded p-1 opacity-0 transition-opacity hover:bg-base-300 group-hover/item:opacity-100 group-focus-within/item:opacity-100"
                              aria-label={`Copy ${task.name} task name`}
                            >
                              <Copy size={14} className="text-base-content/50" />
                            </button>
                          </div>
                        ))}
                      </div>
                    </details>
                  ))}
                </div>
              )}
            </div>
          </div>
          <button
            onClick={() => setIsSidebarVisible((visible) => !visible)}
            className="self-start border-b border-base-300 px-2 py-2 text-base-content/50 hover:bg-base-200 hover:text-base-content"
            aria-label={isSidebarVisible ? "Hide sidebar" : "Show sidebar"}
          >
            <PanelLeft size={16} />
          </button>
        </aside>

        <section className="min-w-0 flex-1">
          {selectedTask && selectedBackend ? (
            <TaskWorkbench task={selectedTask} backend={selectedBackend} />
          ) : (
            <div className="flex h-full items-center justify-center text-base-content/50">
              Select a task to configure and run
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
