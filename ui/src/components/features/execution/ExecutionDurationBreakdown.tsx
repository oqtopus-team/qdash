"use client";

import { useMemo, useState, useEffect } from "react";

import { useQueries } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { getExecution, getGetExecutionQueryKey } from "@/client/execution/execution";
import type { ExecutionResponseDetail, ExecutionResponseSummary, Task } from "@/schemas";

interface ExecutionDurationBreakdownProps {
  executions: ExecutionResponseSummary[];
  selectedTag: string | null;
  onTagSelect: (tag: string | null) => void;
  maxItems?: number;
  allItemsHref?: string;
  padded?: boolean;
  className?: string;
}

interface TaskDurationSample {
  task: Task;
  durationSeconds: number;
}

interface TaskNameDurationStats {
  name: string;
  count: number;
  totalSeconds: number;
  averageSeconds: number;
  medianSeconds: number;
  p95Seconds: number;
  maxSeconds: number;
  successRate: number;
  totalShare: number;
}

const percentile = (values: number[], targetPercentile: number) => {
  if (values.length === 0) return 0;

  const sorted = [...values].sort((a, b) => a - b);
  const index = (sorted.length - 1) * targetPercentile;
  const lower = Math.floor(index);
  const upper = Math.ceil(index);

  if (lower === upper) return sorted[lower];

  return sorted[lower] + (sorted[upper] - sorted[lower]) * (index - lower);
};

const parseElapsedTime = (value: string | null | undefined): number | null => {
  if (!value) return null;

  const trimmed = value.trim();
  const plainSeconds = Number(trimmed);
  if (Number.isFinite(plainSeconds) && plainSeconds > 0) {
    return plainSeconds;
  }

  const dayMatch = trimmed.match(/^(?:(\d+)\s+days?,\s*)?(\d+):(\d{2}):(\d{2}(?:\.\d+)?)$/);
  if (dayMatch) {
    const days = Number(dayMatch[1] ?? 0);
    const hours = Number(dayMatch[2]);
    const minutes = Number(dayMatch[3]);
    const seconds = Number(dayMatch[4]);
    const totalSeconds = days * 86400 + hours * 3600 + minutes * 60 + seconds;
    return totalSeconds > 0 ? totalSeconds : null;
  }

  const unitMatch = trimmed.match(
    /^(?:(\d+(?:\.\d+)?)h\s*)?(?:(\d+(?:\.\d+)?)m\s*)?(?:(\d+(?:\.\d+)?)s)?$/,
  );
  if (unitMatch) {
    const hours = Number(unitMatch[1] ?? 0);
    const minutes = Number(unitMatch[2] ?? 0);
    const seconds = Number(unitMatch[3] ?? 0);
    const totalSeconds = hours * 3600 + minutes * 60 + seconds;
    return totalSeconds > 0 ? totalSeconds : null;
  }

  return null;
};

const getDurationSeconds = (task: Task): number | null => {
  const elapsedSeconds = parseElapsedTime(task.elapsed_time);
  if (elapsedSeconds !== null) return elapsedSeconds;

  if (!task.start_at || !task.end_at) return null;

  const start = new Date(task.start_at).getTime();
  const end = new Date(task.end_at).getTime();
  const durationSeconds = (end - start) / 1000;

  return Number.isFinite(durationSeconds) && durationSeconds > 0 ? durationSeconds : null;
};

const formatDuration = (seconds: number): string => {
  if (seconds === 0) return "N/A";
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`;
  if (seconds < 3600) {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.round(seconds % 60);
    return `${minutes}m ${remainingSeconds}s`;
  }

  const hours = Math.floor(seconds / 3600);
  const minutes = Math.round((seconds % 3600) / 60);
  return `${hours}h ${minutes}m`;
};

export function ExecutionDurationBreakdown({
  executions,
  selectedTag,
  onTagSelect,
  maxItems = 6,
  allItemsHref,
  padded = true,
  className = "",
}: ExecutionDurationBreakdownProps) {
  const [availableTags, setAvailableTags] = useState<string[]>([]);

  // Get list of available tags
  useEffect(() => {
    const tags = new Set<string>();
    executions.forEach((exec) => {
      exec.tags?.forEach((tag) => tags.add(tag));
    });
    setAvailableTags(Array.from(tags));
  }, [executions]);

  // Filter executions by selected tag
  const filteredExecutions = useMemo(() => {
    if (!selectedTag) return executions;
    return executions.filter((exec) => exec.tags?.includes(selectedTag));
  }, [executions, selectedTag]);

  const executionDetailQueries = useQueries({
    queries: filteredExecutions.map((execution) => ({
      queryKey: getGetExecutionQueryKey(execution.execution_id),
      queryFn: ({ signal }) => getExecution(execution.execution_id, undefined, signal),
      enabled: !!execution.execution_id,
      staleTime: 30_000,
      refetchInterval:
        execution.status === "running" ||
        execution.status === "pending" ||
        execution.status === "scheduled"
          ? 5000
          : false,
    })),
  });

  // Calculate statistics
  const stats = useMemo(() => {
    const executionDetails = executionDetailQueries
      .map((query, index) => ({
        executionId: filteredExecutions[index]?.execution_id,
        detail: query.data?.data as ExecutionResponseDetail | undefined,
      }))
      .filter((item): item is { executionId: string; detail: ExecutionResponseDetail } => {
        return !!item.executionId && !!item.detail?.task;
      });

    const allTasks = executionDetails.flatMap(({ detail }) => detail.task);
    const durationSamples: TaskDurationSample[] = allTasks
      .map((task) => {
        const durationSeconds = getDurationSeconds(task);
        if (durationSeconds === null) return null;
        return { task, durationSeconds };
      })
      .filter((sample): sample is TaskDurationSample => sample !== null);

    const taskDurations = durationSamples.map((sample) => sample.durationSeconds);
    const totalTaskSeconds = taskDurations.reduce((total, duration) => total + duration, 0);

    const taskStatsByName = durationSamples.reduce<Record<string, TaskDurationSample[]>>(
      (acc, sample) => {
        const name = sample.task.name || "Unnamed task";
        acc[name] = [...(acc[name] ?? []), sample];
        return acc;
      },
      {},
    );
    const taskBreakdown = Object.entries(taskStatsByName)
      .map<TaskNameDurationStats>(([name, samples]) => {
        const durations = samples.map((sample) => sample.durationSeconds);
        const totalSeconds = durations.reduce((total, duration) => total + duration, 0);
        const completedCount = samples.filter(
          (sample) => sample.task.status === "completed",
        ).length;

        return {
          name,
          count: samples.length,
          totalSeconds,
          averageSeconds: totalSeconds / samples.length,
          medianSeconds: percentile(durations, 0.5),
          p95Seconds: percentile(durations, 0.95),
          maxSeconds: Math.max(...durations),
          successRate: samples.length > 0 ? (completedCount / samples.length) * 100 : 0,
          totalShare: totalTaskSeconds > 0 ? (totalSeconds / totalTaskSeconds) * 100 : 0,
        };
      })
      .sort((a, b) => b.totalSeconds - a.totalSeconds);
    const maxTaskTotalSeconds = taskBreakdown[0]?.totalSeconds ?? 0;

    const longestSingleTask = durationSamples
      .map((sample) => ({
        name: sample.task.name || "Unnamed task",
        durationSeconds: sample.durationSeconds,
      }))
      .sort((a, b) => b.durationSeconds - a.durationSeconds)[0];

    return {
      totalExecutions: filteredExecutions.length,
      loadedExecutions: executionDetails.length,
      totalTasks: allTasks.length,
      totalTaskSeconds,
      tasksWithDuration: durationSamples.length,
      taskBreakdown,
      maxTaskTotalSeconds,
      longestSingleTask,
    };
  }, [executionDetailQueries, filteredExecutions]);

  const isLoadingTaskStats = executionDetailQueries.some((query) => query.isLoading);
  const isTaskStatsPartial = stats.loadedExecutions < filteredExecutions.length;

  const displayedTaskBreakdown =
    maxItems > 0 ? stats.taskBreakdown.slice(0, maxItems) : stats.taskBreakdown;
  const hiddenTaskCount = Math.max(stats.taskBreakdown.length - displayedTaskBreakdown.length, 0);
  const paddingClassName = padded ? "px-4 sm:px-10" : "";

  return (
    <div className={`mb-4 sm:mb-6 ${paddingClassName} ${className}`}>
      {/* Tag filter */}
      <div className="flex flex-wrap gap-1 sm:gap-2 mb-3 sm:mb-4">
        <button
          className={`btn btn-xs sm:btn-sm ${!selectedTag ? "btn-primary" : "btn-ghost"}`}
          onClick={() => onTagSelect(null)}
        >
          All
        </button>
        {availableTags.map((tag) => (
          <button
            key={tag}
            className={`btn btn-xs sm:btn-sm ${selectedTag === tag ? "btn-primary" : "btn-ghost"}`}
            onClick={() => onTagSelect(tag)}
          >
            {tag}
          </button>
        ))}
      </div>

      <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-base-content/60">
        <span>
          Task stats from {stats.loadedExecutions}/{stats.totalExecutions} executions
        </span>
        {isLoadingTaskStats && <span className="loading loading-spinner loading-xs" />}
        {isTaskStatsPartial && !isLoadingTaskStats && <span>Partial data</span>}
      </div>

      <section className="mb-3 sm:mb-4">
        <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2 className="text-sm font-semibold sm:text-base">Task Duration Breakdown</h2>
            <p className="text-xs text-base-content/60">
              Total analyzed time {formatDuration(stats.totalTaskSeconds)} from{" "}
              {stats.tasksWithDuration}/{stats.totalTasks} timed tasks
            </p>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-3">
            {stats.longestSingleTask && (
              <div className="text-right text-xs text-base-content/60">
                <div>Longest single run</div>
                <div className="font-medium text-base-content">
                  {stats.longestSingleTask.name} ·{" "}
                  {formatDuration(stats.longestSingleTask.durationSeconds)}
                </div>
              </div>
            )}
            {allItemsHref && (
              <Link
                href={allItemsHref}
                className="btn btn-primary btn-sm w-full gap-2 whitespace-nowrap sm:w-auto"
              >
                Full breakdown
                <ArrowRight className="h-4 w-4" />
              </Link>
            )}
          </div>
        </div>

        {displayedTaskBreakdown.length === 0 ? (
          <div className="rounded-lg border border-base-300 p-4 text-sm text-base-content/60">
            No task duration samples yet.
          </div>
        ) : (
          <>
            <div className="space-y-3 md:hidden">
              {displayedTaskBreakdown.map((task) => (
                <div key={task.name} className="rounded-lg border border-base-300 p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-semibold">{task.name}</div>
                      <div className="text-xs text-base-content/60">
                        {task.count} runs · {task.successRate.toFixed(0)}% success
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-bold text-primary">
                        {formatDuration(task.totalSeconds)}
                      </div>
                      <div className="text-xs text-base-content/60">
                        {task.totalShare.toFixed(0)}%
                      </div>
                    </div>
                  </div>
                  <progress
                    className="progress progress-primary mt-2 h-1.5 w-full"
                    value={task.totalSeconds}
                    max={stats.maxTaskTotalSeconds || 1}
                  />
                  <div className="mt-2 grid grid-cols-3 gap-2 text-xs">
                    <div>
                      <div className="text-base-content/50">Avg</div>
                      <div className="font-medium">{formatDuration(task.averageSeconds)}</div>
                    </div>
                    <div>
                      <div className="text-base-content/50">Median</div>
                      <div className="font-medium">{formatDuration(task.medianSeconds)}</div>
                    </div>
                    <div>
                      <div className="text-base-content/50">P95</div>
                      <div className="font-medium">{formatDuration(task.p95Seconds)}</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <div className="hidden overflow-x-auto md:block">
              <table className="table table-sm">
                <thead>
                  <tr>
                    <th>Task</th>
                    <th className="w-52">Total Time</th>
                    <th className="text-right">Avg</th>
                    <th className="text-right">Median</th>
                    <th className="text-right">P95</th>
                    <th className="text-right">Max</th>
                    <th className="text-right">Runs</th>
                    <th className="text-right">Success</th>
                  </tr>
                </thead>
                <tbody>
                  {displayedTaskBreakdown.map((task) => (
                    <tr key={task.name}>
                      <td className="max-w-[18rem] truncate font-medium" title={task.name}>
                        {task.name}
                      </td>
                      <td>
                        <div className="flex items-center gap-2">
                          <progress
                            className="progress progress-primary h-1.5 w-24"
                            value={task.totalSeconds}
                            max={stats.maxTaskTotalSeconds || 1}
                          />
                          <span className="whitespace-nowrap font-semibold">
                            {formatDuration(task.totalSeconds)}
                          </span>
                          <span className="whitespace-nowrap text-xs text-base-content/50">
                            {task.totalShare.toFixed(0)}%
                          </span>
                        </div>
                      </td>
                      <td className="text-right tabular-nums">
                        {formatDuration(task.averageSeconds)}
                      </td>
                      <td className="text-right tabular-nums">
                        {formatDuration(task.medianSeconds)}
                      </td>
                      <td className="text-right tabular-nums">{formatDuration(task.p95Seconds)}</td>
                      <td className="text-right tabular-nums">{formatDuration(task.maxSeconds)}</td>
                      <td className="text-right tabular-nums">{task.count}</td>
                      <td className="text-right tabular-nums">{task.successRate.toFixed(0)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {hiddenTaskCount > 0 && (
              <div className="mt-3 flex items-center justify-between rounded-lg border border-base-300 px-3 py-2 text-xs text-base-content/60">
                <span>{hiddenTaskCount} more tasks hidden from this summary.</span>
                {allItemsHref && (
                  <Link
                    href={allItemsHref}
                    className="link link-primary inline-flex items-center gap-1"
                  >
                    Open full breakdown
                    <ArrowRight className="h-3.5 w-3.5" />
                  </Link>
                )}
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}
