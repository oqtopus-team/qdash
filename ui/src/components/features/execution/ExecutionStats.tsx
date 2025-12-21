"use client";

import { useMemo, useState, useEffect } from "react";

import {
  AnimatedCounter,
  AnimatedPercentage,
} from "@/components/ui/AnimatedCounter";
import type { ExecutionResponseSummary } from "@/schemas";

interface ExecutionStatsProps {
  executions: ExecutionResponseSummary[];
  selectedTag: string | null;
  onTagSelect: (tag: string | null) => void;
}

export function ExecutionStats({
  executions,
  selectedTag,
  onTagSelect,
}: ExecutionStatsProps) {
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

  // Calculate statistics
  const stats = useMemo(() => {
    const totalExecutions = filteredExecutions.length;
    const completedExecutions = filteredExecutions.filter(
      (exec) => exec.status === "completed",
    ).length;
    const failedExecutions = filteredExecutions.filter(
      (exec) => exec.status === "failed",
    ).length;
    const runningExecutions = filteredExecutions.filter(
      (exec) => exec.status === "running",
    ).length;

    // Calculate execution times (only completed executions)
    const completedExecutionTimes = filteredExecutions
      .filter(
        (exec) => exec.status === "completed" && exec.start_at && exec.end_at,
      )
      .map((exec) => {
        try {
          const start = new Date(exec.start_at!).getTime();
          const end = new Date(exec.end_at!).getTime();
          const duration = (end - start) / 1000; // In seconds
          return duration > 0 ? duration : 0;
        } catch (error) {
          console.error("Error calculating duration:", error);
          return 0;
        }
      })
      .filter((time) => time > 0);

    const averageTime =
      completedExecutionTimes.length > 0
        ? completedExecutionTimes.reduce((a, b) => a + b, 0) /
          completedExecutionTimes.length
        : 0;

    const maxTime =
      completedExecutionTimes.length > 0
        ? Math.max(...completedExecutionTimes)
        : 0;
    const minTime =
      completedExecutionTimes.length > 0
        ? Math.min(...completedExecutionTimes)
        : 0;

    // Calculate success rate
    const successRate =
      totalExecutions > 0
        ? ((completedExecutions / totalExecutions) * 100).toFixed(1)
        : "0.0";

    return {
      totalExecutions,
      completedExecutions,
      failedExecutions,
      runningExecutions,
      averageTime,
      maxTime,
      minTime,
      successRate,
    };
  }, [filteredExecutions]);

  const formatTime = (seconds: number): string => {
    if (seconds === 0) return "N/A";
    if (seconds < 60) return `${seconds.toFixed(1)}s`;
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}m ${remainingSeconds.toFixed(0)}s`;
  };

  return (
    <div className="mb-4 sm:mb-6 px-4 sm:px-10">
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
            className={`btn btn-xs sm:btn-sm ${
              selectedTag === tag ? "btn-primary" : "btn-ghost"
            }`}
            onClick={() => onTagSelect(tag)}
          >
            {tag}
          </button>
        ))}
      </div>

      {/* Stats cards - Mobile grid */}
      <div className="grid grid-cols-2 gap-2 sm:hidden">
        <div className="bg-base-200 rounded-lg p-3 text-center">
          <div className="text-xs text-base-content/60">Total</div>
          <div className="text-lg font-bold">{stats.totalExecutions}</div>
          <div className="text-xs text-base-content/60">
            {stats.successRate}% success
          </div>
        </div>
        <div className="bg-base-200 rounded-lg p-3 text-center">
          <div className="text-xs text-base-content/60">Status</div>
          <div className="text-lg font-bold text-success">
            {stats.completedExecutions}
          </div>
          <div className="text-xs">
            <span className="text-error">{stats.failedExecutions}F</span>
            {" / "}
            <span className="text-info">{stats.runningExecutions}R</span>
          </div>
        </div>
        <div className="bg-base-200 rounded-lg p-3 text-center">
          <div className="text-xs text-base-content/60">Avg Time</div>
          <div className="text-lg font-bold text-primary">
            {formatTime(stats.averageTime)}
          </div>
        </div>
        <div className="bg-base-200 rounded-lg p-3 text-center">
          <div className="text-xs text-base-content/60">Time Range</div>
          <div className="text-sm font-bold text-secondary">
            {formatTime(stats.minTime)}
          </div>
          <div className="text-xs text-base-content/60">
            - {formatTime(stats.maxTime)}
          </div>
        </div>
      </div>

      {/* Stats cards - Desktop */}
      <div className="hidden sm:grid grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Execution stats */}
        <div className="stats shadow">
          <div className="stat">
            <div className="stat-title">Total Executions</div>
            <div className="stat-value">
              <AnimatedCounter value={stats.totalExecutions} duration={800} />
            </div>
            <div className="stat-desc">
              Success Rate:{" "}
              <AnimatedPercentage
                value={parseFloat(stats.successRate)}
                duration={800}
              />
            </div>
          </div>
        </div>

        {/* Status breakdown */}
        <div className="stats shadow">
          <div className="stat">
            <div className="stat-title">Status</div>
            <div className="stat-value text-success">
              <AnimatedCounter
                value={stats.completedExecutions}
                duration={800}
              />
            </div>
            <div className="stat-desc">
              <span className="text-success">Completed</span> /{" "}
              <span className="text-error">
                <AnimatedCounter
                  value={stats.failedExecutions}
                  duration={800}
                />{" "}
                Failed
              </span>{" "}
              /{" "}
              <span className="text-info">
                <AnimatedCounter
                  value={stats.runningExecutions}
                  duration={800}
                />{" "}
                Running
              </span>
            </div>
          </div>
        </div>

        {/* Average execution time */}
        <div className="stats shadow">
          <div className="stat">
            <div className="stat-title">Average Time</div>
            <div className="stat-value text-primary">
              {formatTime(stats.averageTime)}
            </div>
            <div className="stat-desc">Per execution</div>
          </div>
        </div>

        {/* Execution time range */}
        <div className="stats shadow">
          <div className="stat">
            <div className="stat-title">Time Range</div>
            <div className="stat-value text-secondary">
              {formatTime(stats.minTime)} - {formatTime(stats.maxTime)}
            </div>
            <div className="stat-desc">Min - Max</div>
          </div>
        </div>
      </div>
    </div>
  );
}
