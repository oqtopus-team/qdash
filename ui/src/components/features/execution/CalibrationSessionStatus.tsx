"use client";

import { Circle, CircleDot, type LucideIcon } from "lucide-react";

import type { CalibrationSessionStatus } from "@/schemas";

import { getStatusBadgeClass, getStatusBorderStyle } from "./ExecutionListCard";

type CalibrationSessionStatusStyle = {
  label: string;
  badge: string;
  border: string;
  Icon: LucideIcon;
};

/**
 * A calibration session's state in the Execution status palette. Open reads like an active
 * execution. Closed reads like a completed execution so a finished session is easy to spot: all
 * of its work has ended. The color does not mean every run succeeded; each child execution keeps
 * its own result color.
 */
export function calibrationSessionStatusStyle(
  status: CalibrationSessionStatus,
): CalibrationSessionStatusStyle {
  if (status === "open") {
    return {
      label: "Open",
      badge: getStatusBadgeClass("running"),
      border: getStatusBorderStyle("running"),
      Icon: CircleDot,
    };
  }
  return {
    label: "Closed",
    badge: getStatusBadgeClass("completed"),
    border: getStatusBorderStyle("completed"),
    Icon: Circle,
  };
}

/** Left accent of a calibration session card, matching the execution card of the same color. */
export function calibrationSessionBorderStyle(status: CalibrationSessionStatus): string {
  return calibrationSessionStatusStyle(status).border;
}

/** Open or closed, shaped like the execution status badge: an icon and its text. */
export function CalibrationSessionStatusBadge({ status }: { status: CalibrationSessionStatus }) {
  const { label, badge, Icon } = calibrationSessionStatusStyle(status);
  return (
    <span className={`badge badge-sm shrink-0 gap-1 ${badge}`} data-status={status}>
      <Icon className="h-4 w-4" aria-hidden="true" />
      {label}
    </span>
  );
}
