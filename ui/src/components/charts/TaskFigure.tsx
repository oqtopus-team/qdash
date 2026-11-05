"use client";

import { useEffect, useState } from "react";
import { RotateCw, ZoomIn } from "lucide-react";

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

/** Delays before each automatic reload of a figure that failed to load, in milliseconds. */
export const FIGURE_RETRY_DELAYS_MS: readonly number[] = [1000, 3000];

interface FigureLoadState {
  src: string;
  /** Loads after the first; each one asks the browser for the image again. */
  attempt: number;
  /** Waiting to reload after a failed load. */
  waiting: boolean;
  failed: boolean;
}

function freshLoadState(src: string): FigureLoadState {
  return { src, attempt: 0, waiting: false, failed: false };
}

/**
 * Loads a figure URL and recovers from transient failures. A figure can fail to load while the
 * API restarts or a request is dropped; the browser keeps that failure, so the URL is requested
 * again a few times with a retry marker before the figure reports an error. A new figure path
 * always starts from a fresh load, so a failure never carries over to another figure.
 */
function useRetryingFigureSrc(src: string) {
  const [state, setState] = useState<FigureLoadState>(() => freshLoadState(src));
  const current = state.src === src ? state : freshLoadState(src);
  if (state.src !== src) setState(current);

  useEffect(() => {
    if (!current.waiting) return;
    const delay = FIGURE_RETRY_DELAYS_MS[current.attempt] ?? 0;
    const timer = window.setTimeout(() => {
      setState((previous) =>
        previous.src === src && previous.waiting
          ? { ...previous, attempt: previous.attempt + 1, waiting: false }
          : previous,
      );
    }, delay);
    return () => window.clearTimeout(timer);
  }, [current.waiting, current.attempt, src]);

  const onError = () =>
    setState((previous) => {
      if (previous.src !== src || previous.waiting) return previous;
      return previous.attempt < FIGURE_RETRY_DELAYS_MS.length
        ? { ...previous, waiting: true }
        : { ...previous, failed: true };
    });
  const retry = () =>
    setState((previous) => ({
      src,
      attempt: previous.src === src ? previous.attempt + 1 : 0,
      waiting: false,
      failed: false,
    }));

  const requestSrc =
    current.attempt === 0 ? src : `${src}${src.includes("?") ? "&" : "?"}retry=${current.attempt}`;
  return { requestSrc, waiting: current.waiting, failed: current.failed, onError, retry };
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
  const { requestSrc, waiting, failed, onError, retry } = useRetryingFigureSrc(src);

  if (failed) {
    return (
      <div
        role="alert"
        className="flex h-full flex-col items-center justify-center gap-1 text-xs text-base-content/60"
      >
        <span>Failed to load image</span>
        <button
          type="button"
          className="btn btn-xs btn-ghost gap-1"
          onClick={(event) => {
            event.stopPropagation();
            retry();
          }}
        >
          <RotateCw className="h-3 w-3" aria-hidden="true" />
          Retry
        </button>
      </div>
    );
  }

  if (waiting) {
    return (
      <div className="flex h-full items-center justify-center" aria-busy="true">
        <span className="loading loading-spinner loading-sm" aria-label="Loading figure" />
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
        src={requestSrc}
        alt={alt}
        className={fit ? `h-full w-full object-contain ${className}` : className}
        onError={onError}
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
          src={requestSrc}
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
    <div className="flex h-full w-full items-center gap-2 overflow-x-auto">
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
    </div>
  );
}
