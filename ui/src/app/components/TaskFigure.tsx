"use client";

import { useGetTaskResult } from "@/client/task/task";

interface TaskFigureProps {
  path?: string | string[];
  taskId?: string;
  qid: string;
  className?: string;
}

export function TaskFigure({
  path,
  taskId,
  qid,
  className = "",
}: TaskFigureProps) {
  // Use /api proxy route (handled by Next.js rewrites)
  const apiUrl = "/api";

  // Use generated API client hook when taskId is provided
  const {
    data: taskResultResponse,
    isLoading: loading,
    error: fetchError,
  } = useGetTaskResult(taskId!, {
    query: {
      enabled: !!taskId && !path,
    },
  });

  const taskResult = taskResultResponse?.data;
  const error = fetchError?.message || null;

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

  // Use fetched task result if available (prefer static images over JSON)
  const figurePaths =
    path || taskResult?.figure_path || taskResult?.json_figure_path || [];

  if (Array.isArray(figurePaths) && figurePaths.length > 0) {
    return (
      <>
        {figurePaths.map((p, i) => (
          <img
            key={i}
            src={`${apiUrl}/executions/figure?path=${encodeURIComponent(p)}`}
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
        src={`${apiUrl}/executions/figure?path=${encodeURIComponent(figurePaths)}`}
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
