"use client";

import React, { useState } from "react";
import { ZoomIn } from "lucide-react";

import { useGetTaskResult } from "@/client/task/task";
import { FigureLightbox } from "./FigureLightbox";

interface TaskFigureProps {
  path?: string | string[];
  taskId?: string;
  qid: string;
  className?: string;
}

function ExpandableImage({
  src,
  alt,
  className,
}: {
  src: string;
  alt: string;
  className: string;
}) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="relative group inline-flex h-full shrink-0">
      <img src={src} alt={alt} className={className} />
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        className="absolute top-1 right-1 opacity-0 group-hover:opacity-100 transition-opacity btn btn-xs btn-circle bg-base-100/80 shadow hover:bg-base-200"
        title="Expand"
      >
        <ZoomIn className="h-3 w-3" />
      </button>
      {isOpen && (
        <FigureLightbox src={src} alt={alt} onClose={() => setIsOpen(false)} />
      )}
    </div>
  );
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
  const error = (fetchError as Error)?.message || null;

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
          <ExpandableImage
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
      <ExpandableImage
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
