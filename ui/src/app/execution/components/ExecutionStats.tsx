"use client";

import { useMemo, useState, useEffect } from "react";

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

  // タグの一覧を取得
  useEffect(() => {
    const tags = new Set<string>();
    executions.forEach((exec) => {
      exec.tags?.forEach((tag) => tags.add(tag));
    });
    setAvailableTags(Array.from(tags));
  }, [executions]);

  // 選択されたタグでフィルタリング
  const filteredExecutions = useMemo(() => {
    if (!selectedTag) return executions;
    return executions.filter((exec) => exec.tags?.includes(selectedTag));
  }, [executions, selectedTag]);
  // 統計情報の計算
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

    // 実行時間の計算（完了した実行のみ対象）
    const completedExecutionTimes = filteredExecutions
      .filter(
        (exec) => exec.status === "completed" && exec.start_at && exec.end_at,
      )
      .map((exec) => {
        try {
          const start = new Date(exec.start_at).getTime();
          const end = new Date(exec.end_at).getTime();
          const duration = (end - start) / 1000; // 秒単位
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

    // 成功率の計算
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
    <div className="mb-6 px-10">
      {/* タグフィルター */}
      <div className="flex flex-wrap gap-2 mb-4">
        <button
          className={`btn btn-sm ${!selectedTag ? "btn-primary" : "btn-ghost"}`}
          onClick={() => onTagSelect(null)}
        >
          All
        </button>
        {availableTags.map((tag) => (
          <button
            key={tag}
            className={`btn btn-sm ${
              selectedTag === tag ? "btn-primary" : "btn-ghost"
            }`}
            onClick={() => onTagSelect(tag)}
          >
            {tag}
          </button>
        ))}
      </div>

      {/* 統計カード */}
      <div className="grid grid-cols-4 gap-4">
        {/* 実行統計 */}
        <div className="stats shadow">
          <div className="stat">
            <div className="stat-title">Total Executions</div>
            <div className="stat-value">{stats.totalExecutions}</div>
            <div className="stat-desc">Success Rate: {stats.successRate}%</div>
          </div>
        </div>

        {/* ステータス内訳 */}
        <div className="stats shadow">
          <div className="stat">
            <div className="stat-title">Status</div>
            <div className="stat-value text-success">
              {stats.completedExecutions}
            </div>
            <div className="stat-desc">
              <span className="text-success">Completed</span> /{" "}
              <span className="text-error">
                {stats.failedExecutions} Failed
              </span>{" "}
              /{" "}
              <span className="text-info">
                {stats.runningExecutions} Running
              </span>
            </div>
          </div>
        </div>

        {/* 平均実行時間 */}
        <div className="stats shadow">
          <div className="stat">
            <div className="stat-title">Average Time</div>
            <div className="stat-value text-primary">
              {formatTime(stats.averageTime)}
            </div>
            <div className="stat-desc">Per execution</div>
          </div>
        </div>

        {/* 実行時間範囲 */}
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
