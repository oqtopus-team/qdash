"use client";

import { useState } from "react";
import { ZoomIn } from "lucide-react";

import { FigureStrip } from "@/components/charts/FigureStrip";
import { useGetTaskResult } from "@/client/task/task";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/Tooltip";
import { FigureLightbox } from "./FigureLightbox";

interface TaskFigureProps {
  path?: string | string[];
  jsonFigurePath?: string | string[];
  taskId?: string;
  qid: string;
  className?: string;
  hideExpandButton?: boolean;
  /**
   * Scale the figure down to fit its box (both width and height), centred.
   * Without it the figure keeps its height and overflows sideways, which suits
   * the horizontally scrolling strips most pages put figures in.
   */
  fit?: boolean;
}

function figureUrl(path: string): string {
  return `/api/executions/figure?path=${encodeURIComponent(path)}`;
}

function ExpandableImage({
  src,
  alt,
  className,
  jsonFigurePath,
  hideExpandButton,
  fit = false,
}: {
  src: string;
  alt: string;
  className: string;
  jsonFigurePath?: string;
  hideExpandButton?: boolean;
  fit?: boolean;
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
    <div
      className={
        fit
          ? "relative group flex h-full w-full min-w-0 min-h-0 items-center justify-center"
          : "relative group inline-flex h-full min-w-0 min-h-0 shrink-0"
      }
    >
      {/* eslint-disable-next-line @next/next/no-img-element -- dynamic API image with native sizing */}
      <img
        src={src}
        alt={alt}
        className={fit ? `h-full w-full object-contain ${className}` : className}
        onError={() => setHasError(true)}
      />
      {!hideExpandButton && (
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setIsOpen(true);
              }}
              className="absolute top-1 right-1 opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-opacity btn btn-xs btn-circle bg-base-100/80 shadow hover:bg-base-200"
              aria-label="Expand figure"
            >
              <ZoomIn className="h-3 w-3" />
            </button>
          </TooltipTrigger>
          <TooltipContent>Expand figure</TooltipContent>
        </Tooltip>
      )}
      {isOpen && (
        <FigureLightbox
          src={src}
          alt={alt}
          jsonFigurePath={jsonFigurePath}
          onClose={() => setIsOpen(false)}
        />
      )}
    </div>
  );
}

export function TaskFigure({
  path,
  jsonFigurePath,
  taskId,
  qid,
  className = "",
  hideExpandButton,
  fit = false,
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
  const raw = path || taskResult?.figure_path || taskResult?.json_figure_path || [];
  const normalizedPaths = Array.isArray(raw) ? raw : typeof raw === "string" ? [raw] : [];

  // Normalize json figure paths
  const rawJson = jsonFigurePath || taskResult?.json_figure_path || [];
  const normalizedJsonPaths = Array.isArray(rawJson)
    ? rawJson
    : typeof rawJson === "string"
      ? [rawJson]
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
        jsonFigurePath={normalizedJsonPaths[0]}
        hideExpandButton={hideExpandButton}
        fit={fit}
      />
    );
  }

  return (
    <FigureStrip className="h-full w-full gap-2">
      {normalizedPaths.map((p, i) => (
        <ExpandableImage
          key={p}
          src={figureUrl(p)}
          alt={`Result for QID ${qid}`}
          className={className}
          jsonFigurePath={normalizedJsonPaths[i]}
          hideExpandButton={hideExpandButton}
        />
      ))}
    </FigureStrip>
  );
}
