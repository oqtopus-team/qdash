"use client";

import { useState, useEffect } from "react";

interface TaskFigureProps {
  path?: string | string[];
  taskId?: string;
  qid: string;
  className?: string;
}

interface TaskResult {
  figure_path: string[];
  json_figure_path: string[];
}

export function TaskFigure({
  path,
  taskId,
  chipId: _chipId,
  qid,
  className = "",
}: TaskFigureProps) {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;
  const [taskResult, setTaskResult] = useState<TaskResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch task result if taskId is provided
  useEffect(() => {
    if (taskId && !path) {
      setLoading(true);
      fetch(`${apiUrl}/api/chip/task/${taskId}`, {
        headers: {
          "X-Username": "admin", // TODO: Get from auth context
        },
      })
        .then((res) => {
          if (!res.ok) throw new Error("Failed to fetch task result");
          return res.json();
        })
        .then((data) => {
          setTaskResult(data);
          setLoading(false);
        })
        .catch((err) => {
          setError(err.message);
          setLoading(false);
        });
    }
  }, [taskId, path, apiUrl]);

  // Loading state
  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <span className="loading loading-spinner loading-lg"></span>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="alert alert-error">
        <span>Error loading figure: {error}</span>
      </div>
    );
  }

  // Use fetched task result if available
  const figurePaths =
    path || taskResult?.json_figure_path || taskResult?.figure_path || [];

  if (Array.isArray(figurePaths) && figurePaths.length > 0) {
    return (
      <>
        {figurePaths.map((p, i) => (
          <img
            key={i}
            src={`${apiUrl}/api/executions/figure?path=${encodeURIComponent(
              p,
            )}`}
            alt={`Result for QID ${qid}`}
            className={className}
          />
        ))}
      </>
    );
  }

  if (typeof figurePaths === "string") {
    return (
      <img
        src={`${apiUrl}/api/executions/figure?path=${encodeURIComponent(figurePaths)}`}
        alt={`Result for QID ${qid}`}
        className={className}
      />
    );
  }

  // No figure available
  return (
    <div className="alert alert-info">
      <span>No figure available for this task</span>
    </div>
  );
}
