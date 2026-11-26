"use client";

import { LoaderCircle, Minimize } from "lucide-react";

function requestErrorMessage(error: unknown): string | null {
  if (!error || typeof error !== "object") return null;
  const response = (error as { response?: { data?: unknown } }).response;
  const data = response?.data;
  if (!data || typeof data !== "object") return null;
  const detail = (data as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item) => JSON.stringify(item)).join("; ");
  return null;
}

function taskRangeLabel(
  selectedDate: string,
  startAt?: string | null,
  endAt?: string | null,
): string {
  if (startAt || endAt) return `${startAt ?? "..."} - ${endAt ?? "..."}`;
  return selectedDate;
}

interface GridLoadingPanelProps {
  className: string;
  isFullscreen: boolean;
  onExitFullscreen: () => void;
}

/** Initial-load state of a chip grid, keeping the fullscreen exit reachable. */
export function GridLoadingPanel({
  className,
  isFullscreen,
  onExitFullscreen,
}: GridLoadingPanelProps) {
  return (
    <div className={className}>
      {isFullscreen && (
        <div className="flex justify-end">
          <button
            onClick={onExitFullscreen}
            className="btn btn-sm btn-square btn-ghost"
            title="Exit fullscreen (Esc)"
            aria-label="Exit fullscreen"
          >
            <Minimize className="h-4 w-4" />
          </button>
        </div>
      )}
      <div className="w-full flex flex-1 items-center justify-center py-12">
        <span className="loading loading-spinner loading-lg"></span>
      </div>
    </div>
  );
}

interface GridTaskRequestAlertsProps {
  selectedTask: string;
  selectedDate: string;
  startAt?: string | null;
  endAt?: string | null;
  /** A background refetch is running while earlier results stay visible. */
  isRefreshing: boolean;
  isError: boolean;
  error: unknown;
}

/** Refresh progress and failure of a chip grid's task results, named by task and range. */
export function GridTaskRequestAlerts({
  selectedTask,
  selectedDate,
  startAt,
  endAt,
  isRefreshing,
  isError,
  error,
}: GridTaskRequestAlertsProps) {
  const rangeLabel = taskRangeLabel(selectedDate, startAt, endAt);
  const errorDetail = requestErrorMessage(error);
  return (
    <>
      {isRefreshing && (
        <div className="alert alert-info py-2 text-sm">
          <LoaderCircle className="h-4 w-4 animate-spin" />
          Loading {selectedTask} data for {rangeLabel}
        </div>
      )}
      {isError && (
        <div className="alert alert-error text-sm">
          <span>
            Failed to load {selectedTask} data for {rangeLabel}
            {errorDetail ? `: ${errorDetail}` : ""}
          </span>
        </div>
      )}
    </>
  );
}
