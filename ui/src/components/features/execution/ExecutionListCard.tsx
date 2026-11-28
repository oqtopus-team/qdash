"use client";

import type { ReactNode } from "react";

import {
  Ban,
  CircleCheck,
  CircleHelp,
  CirclePlay,
  CircleX,
  Clock,
  StopCircle,
  type LucideIcon,
} from "lucide-react";

import type { ExecutionResponseSummary } from "@/schemas";

import { formatDateTime } from "@/lib/utils/datetime";

import { ExecutionActor } from "./ExecutionAttribution";
import { CalibrationSessionBadge } from "./ExecutionCalibrationContext";

export { recordedUserLabel as formatActorLabel } from "./ExecutionAttribution";

function getStatusLabel(status: string) {
  return status.charAt(0).toUpperCase() + status.slice(1);
}

export function getStatusBadgeClass(status: string) {
  switch (status) {
    case "running":
      return "badge-info";
    case "completed":
      return "badge-success";
    case "scheduled":
    case "pending":
      return "badge-warning";
    case "failed":
      return "badge-error";
    default:
      return "badge-ghost";
  }
}

// Static icons pair each status color with a shape, so running and cancelling stay
// recognizable without a continuous pulse and status never relies on color alone.
export function getStatusIcon(status: string): LucideIcon {
  switch (status) {
    case "running":
      return CirclePlay;
    case "completed":
      return CircleCheck;
    case "scheduled":
    case "pending":
      return Clock;
    case "failed":
      return CircleX;
    case "cancelling":
      return StopCircle;
    case "cancelled":
      return Ban;
    default:
      return CircleHelp;
  }
}

export function getStatusBorderStyle(status: string) {
  switch (status) {
    case "running":
      return "border-l-4 border-l-info";
    case "completed":
      return "border-l-4 border-l-success";
    case "scheduled":
      return "border-l-4 border-l-warning";
    case "failed":
      return "border-l-4 border-l-error";
    case "cancelled":
    case "cancelling":
      return "border-l-4 border-l-neutral";
    default:
      return "border-l-4 border-l-base-300";
  }
}

interface ExecutionListCardProps {
  execution: ExecutionResponseSummary;
  isSelected: boolean;
  isPanelOpen: boolean;
  onOpen: (execution: ExecutionResponseSummary) => void;
  registerCard: (executionId: string, element: HTMLDivElement | null) => void;
  /** Shown before the name, such as the step of an agent session. */
  prefix?: ReactNode;
  /** Shown under the meta line. */
  footer?: ReactNode;
}

/** One execution of the Execution list; selecting it opens the details panel. */
export function ExecutionListCard({
  execution,
  isSelected,
  isPanelOpen,
  onOpen,
  registerCard,
  prefix,
  footer,
}: ExecutionListCardProps) {
  const StatusIcon = getStatusIcon(execution.status);
  return (
    <div
      ref={(element) => registerCard(execution.execution_id, element)}
      role="button"
      aria-expanded={isSelected && isPanelOpen}
      aria-controls="execution-details-panel"
      tabIndex={0}
      aria-label={`View ${execution.name} execution details`}
      className={`relative flex cursor-pointer overflow-hidden rounded-box border border-base-200 bg-base-100 p-3 shadow-sm transition-colors hover:border-primary/40 hover:bg-base-200/40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary sm:p-4 ${getStatusBorderStyle(execution.status)}`}
      onClick={() => onOpen(execution)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen(execution);
        }
      }}
    >
      {isSelected && (
        <div className="absolute inset-0 bg-primary opacity-10 pointer-events-none transition-opacity duration-500" />
      )}
      <div className="relative z-10 w-full">
        <div className="flex items-center justify-between gap-2">
          <h3 className="flex min-w-0 items-center gap-2 text-sm font-medium">
            {prefix}
            <span className="truncate">{execution.name}</span>
          </h3>
          <span
            className={`badge badge-sm flex-shrink-0 gap-1 ${getStatusBadgeClass(execution.status)}`}
          >
            <StatusIcon className="h-4 w-4" aria-hidden="true" />
            {getStatusLabel(execution.status)}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-x-2 sm:gap-x-3 gap-y-0.5 mt-0.5 sm:mt-1 text-sm text-base-content/60">
          <span>{formatDateTime(execution.start_at)}</span>
          {execution.elapsed_time && (
            <span className="hidden sm:inline">Duration: {execution.elapsed_time}</span>
          )}
          {execution.elapsed_time && <span className="sm:hidden">{execution.elapsed_time}</span>}
          <ExecutionActor
            actor={execution}
            link={execution.agent_session}
            origin={execution.reported_origin}
          />
          {execution.calibration_session ? (
            <CalibrationSessionBadge link={execution.calibration_session} />
          ) : null}
        </div>
        {execution.status === "failed" && execution.message && (
          <p className="mt-2 line-clamp-2 text-xs text-error">{execution.message}</p>
        )}
        {footer}
      </div>
    </div>
  );
}
