"use client";

import { createPortal } from "react-dom";

import { formatDateTime } from "@/lib/utils/datetime";

import type { NoteEntryWithMetric, TargetNoteEntry } from "./MetricNotePanel";

export interface ForumLinkEntry {
  id: string;
  number?: number | null;
  title?: string | null;
  labels?: string[];
  status?: string | null;
  replyCount?: number | null;
}

function targetNoteComments(targetNote: TargetNoteEntry) {
  return (targetNote.comments ?? []).filter((comment) => comment.content?.trim());
}

function hasTargetNoteContent(targetNote: TargetNoteEntry): boolean {
  return !!targetNote.content.trim() || targetNoteComments(targetNote).length > 0;
}

interface DashboardNoteTooltipProps {
  /** Anchor position in viewport coordinates (top-center of the source cell). */
  position: { x: number; y: number };
  /** Header — e.g. "Q5 · T1: 23.4 us". */
  header: string;
  /** Shared target-level note for this qubit/coupling. */
  targetNote?: TargetNoteEntry;
  /** Legacy note for the current metric, if any. */
  current?: NoteEntryWithMetric;
  /** Notes for the same target on other metrics. Renders as a list. */
  others?: NoteEntryWithMetric[];
  /** Linked forum discussions for this target in the selected context. */
  forumLinks?: ForumLinkEntry[];
}

/**
 * Portal-based hover tooltip that shows note content for a cell. Positioned
 * above the cell with a small offset.
 */
export function DashboardNoteTooltip({
  position,
  header,
  targetNote,
  current,
  others,
  forumLinks,
}: DashboardNoteTooltipProps) {
  if (typeof document === "undefined") return null;
  const hasForumLinks = !!forumLinks && forumLinks.length > 0;
  const hasTargetNote = targetNote ? hasTargetNoteContent(targetNote) : false;
  const targetComments = targetNote ? targetNoteComments(targetNote) : [];
  if (!hasTargetNote && !current && (!others || others.length === 0) && !hasForumLinks) {
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
      className="px-3 py-2 bg-base-100 text-base-content text-xs rounded-lg shadow-lg pointer-events-none border border-base-300 max-w-md max-h-[min(28rem,calc(100vh-2rem))] overflow-hidden space-y-2"
      style={{
        position: "fixed",
        left: position.x,
        top: position.y - 8,
        transform: "translate(-50%, -100%)",
        zIndex: 9999,
      }}
    >
      <div className="font-semibold tabular-nums">{header}</div>
      {hasTargetNote && targetNote && (
        <div className="space-y-1.5 border-l-2 border-warning pl-2">
          <div className="text-[10px] uppercase tracking-wide text-warning">
            pinned summary
            {targetComments.length > 0 ? ` (${targetComments.length})` : ""}
          </div>
          {targetNote.content.trim() && (
            <div>
              <p className="whitespace-pre-wrap break-words">{targetNote.content}</p>
              <div className="text-[10px] text-base-content/50 mt-0.5">
                {targetNote.username || "-"}
                {targetNote.updatedAt ? ` · ${formatDateTime(targetNote.updatedAt)}` : ""}
              </div>
            </div>
          )}
          {targetComments.length > 0 && (
            <ul className="space-y-1.5">
              {targetComments.slice(-3).map((comment) => (
                <li key={comment.comment_id || `${comment.created_by}-${comment.created_at}`}>
                  <p className="whitespace-pre-wrap break-words">{comment.content}</p>
                  <div className="text-[10px] text-base-content/50 mt-0.5">
                    {comment.created_by || "-"}
                    {comment.created_at ? ` · ${formatDateTime(comment.created_at)}` : ""}
                  </div>
                </li>
              ))}
              {targetComments.length > 3 && (
                <li className="text-[10px] text-base-content/50">
                  +{targetComments.length - 3} earlier entries
                </li>
              )}
            </ul>
          )}
        </div>
      )}
      {current && (
        <div className="border-l-2 border-base-300 pl-2">
          <div className="text-[10px] uppercase tracking-wide text-base-content/60">
            legacy metric note
          </div>
          <p className="whitespace-pre-wrap break-words">{current.content}</p>
          <div className="text-[10px] text-base-content/50 mt-0.5">
            {current.username} · {formatDateTime(current.updatedAt)}
          </div>
        </div>
      )}
      {hasForumLinks && (
        <div className="space-y-1.5 border-l-2 border-info pl-2">
          <div className="text-[10px] uppercase tracking-wide text-info">
            linked forum discussions ({forumLinks.length})
          </div>
          <ul className="space-y-1.5">
            {forumLinks.slice(0, 6).map((post) => (
              <li key={post.id}>
                <div className="font-semibold text-[11px]">
                  {post.number ? `#${post.number} ` : ""}
                  {post.title?.trim() || "Untitled discussion"}
                </div>
                <div className="text-[10px] text-base-content/50">
                  {post.status || "open"} · {post.replyCount ?? 0} replies
                  {post.labels && post.labels.length > 0 ? ` · ${post.labels.join(", ")}` : ""}
                </div>
              </li>
            ))}
            {forumLinks.length > 6 && (
              <li className="text-[10px] text-base-content/50">
                +{forumLinks.length - 6} more discussions
              </li>
            )}
          </ul>
        </div>
      )}
      {others && others.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-[10px] uppercase tracking-wide text-base-content/60">
            legacy notes on other metrics ({others.length})
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
