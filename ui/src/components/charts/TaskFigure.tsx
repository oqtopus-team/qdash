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

function figureUrl(path: string): string {
  return `/api/executions/figure?path=${encodeURIComponent(path)}`;
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
  const [hasError, setHasError] = useState(false);

  if (hasError) {
    return (
      <div className="flex items-center justify-center h-full text-base-content/40 text-xs">
        Failed to load image
      </div>
    );
  }

  return (
    <div className="relative group inline-flex h-full min-w-0 min-h-0">
      <img
        src={src}
        alt={alt}
        className={className}
        onError={() => setHasError(true)}
      />
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setIsOpen(true);
        }}
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

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <span className="loading loading-spinner loading-lg"></span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="alert alert-error">
        <span>Error loading figure: {error}</span>
      </div>
    );
  }

  // Normalize to string array
  const raw =
    path || taskResult?.figure_path || taskResult?.json_figure_path || [];
  const normalizedPaths = Array.isArray(raw)
    ? raw
    : typeof raw === "string"
      ? [raw]
      : [];

  if (normalizedPaths.length === 0) {
    return (
      <div className="alert alert-info">
        <span>No figure available for this task</span>
      </div>
    );
  }

  if (normalizedPaths.length === 1) {
    return (
      <ExpandableImage
        src={figureUrl(normalizedPaths[0])}
        alt={`Result for QID ${qid}`}
        className={className}
      />
    );
  }

  return (
    <div className="flex flex-wrap gap-2 overflow-hidden w-full h-full">
      {normalizedPaths.map((p) => (
        <ExpandableImage
          key={p}
          src={figureUrl(p)}
          alt={`Result for QID ${qid}`}
          className={`${className} max-w-full max-h-full`}
        />
      ))}
    </div>
  );
}
