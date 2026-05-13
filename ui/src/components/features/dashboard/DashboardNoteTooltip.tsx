"use client";

import { createPortal } from "react-dom";

import { formatDateTime } from "@/lib/utils/datetime";

import type { NoteEntryWithMetric } from "./MetricNotePanel";

interface DashboardNoteTooltipProps {
  /** Anchor position in viewport coordinates (top-center of the source cell). */
  position: { x: number; y: number };
  /** Header — e.g. "Q5 · T1: 23.4 us". */
  header: string;
  /** Note for the current metric, if any. Renders prominently. */
  current?: NoteEntryWithMetric;
  /** Notes for the same target on other metrics. Renders as a list. */
  others?: NoteEntryWithMetric[];
}

/**
 * Portal-based hover tooltip that shows note content for a cell. Positioned
 * above the cell with a small offset.
 */
export function DashboardNoteTooltip({
  position,
  header,
  current,
  others,
}: DashboardNoteTooltipProps) {
  if (typeof document === "undefined") return null;
  if (!current && (!others || others.length === 0)) {
    // No notes at all — render only the header so users still get value/unit info.
    return createPortal(
      <div
        role="tooltip"
        className="px-3 py-2 bg-base-100 text-base-content text-xs rounded-lg shadow-lg whitespace-nowrap pointer-events-none border border-base-300"
        style={{
          position: "fixed",
          left: position.x,
          top: position.y - 8,
          transform: "translate(-50%, -100%)",
          zIndex: 9999,
        }}
      >
        {header}
      </div>,
      document.body,
    );
  }

  return createPortal(
    <div
      role="tooltip"
      className="px-3 py-2 bg-base-100 text-base-content text-xs rounded-lg shadow-lg pointer-events-none border border-base-300 max-w-sm space-y-2"
      style={{
        position: "fixed",
        left: position.x,
        top: position.y - 8,
        transform: "translate(-50%, -100%)",
        zIndex: 9999,
      }}
    >
      <div className="font-semibold tabular-nums">{header}</div>
      {current && (
        <div className="border-l-2 border-warning pl-2">
          <div className="text-[10px] uppercase tracking-wide text-warning">this metric</div>
          <p className="whitespace-pre-wrap break-words">{current.content}</p>
          <div className="text-[10px] text-base-content/50 mt-0.5">
            {current.username} · {formatDateTime(current.updatedAt)}
          </div>
        </div>
      )}
      {others && others.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-[10px] uppercase tracking-wide text-base-content/60">
            other metrics ({others.length})
          </div>
          <ul className="space-y-1.5">
            {others.map((n) => (
              <li key={n.metricKey} className="border-l-2 border-base-300 pl-2">
                <div className="font-semibold text-[11px]">{n.metricTitle}</div>
                <p className="whitespace-pre-wrap break-words text-base-content/80">{n.content}</p>
                <div className="text-[10px] text-base-content/50">
                  {n.username} · {formatDateTime(n.updatedAt)}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>,
    document.body,
  );
}
