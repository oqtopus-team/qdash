"use client";

import { useMemo } from "react";

import Link from "next/link";
import { ExternalLink, StickyNote } from "lucide-react";

import { formatDate } from "@/lib/utils/datetime";

import type { NoteEntryWithMetric } from "./MetricNotePanel";

interface TaskNoteEntry {
  taskId: string;
  qid: string;
  content: string;
  username: string;
  updatedAt: string;
}

interface DashboardNotesSummaryProps {
  /** Per-(target, metric) chip notes indexed by target_id. */
  notesByTarget: Record<string, NoteEntryWithMetric[]>;
  /** Per-task_result notes for this chip. */
  taskNotes: TaskNoteEntry[];
  /** Triggered when a chip-note row is clicked — opens the metric modal. */
  onEdit: (entry: NoteEntryWithMetric) => void;
}

function formatTarget(targetId: string): string {
  if (targetId.includes("-")) {
    const [a, b] = targetId.split("-");
    return `Q${a} → Q${b}`;
  }
  return `Q${targetId}`;
}

function compareTargets(a: string, b: string): number {
  // Qubits first (no "-"), then couplings. Within a group, numeric sort.
  const aIsCoupling = a.includes("-");
  const bIsCoupling = b.includes("-");
  if (aIsCoupling !== bIsCoupling) return aIsCoupling ? 1 : -1;
  return a.localeCompare(b, undefined, { numeric: true });
}

function isAiGeneratedNote(content: string, username: string): boolean {
  const lead = content
    .trimStart()
    .replace(/^#{1,6}\s*/, "")
    .replace(/^\*\*/, "")
    .toLowerCase();

  return (
    lead.startsWith("ai review") ||
    lead.startsWith("ai triage") ||
    (username === "qdash-ai" && /\b(?:review|triage)\b/i.test(lead.slice(0, 120)))
  );
}

export function DashboardNotesSummary({
  notesByTarget,
  taskNotes,
  onEdit,
}: DashboardNotesSummaryProps) {
  const visibleNotesByTarget = useMemo(() => {
    const entries = Object.entries(notesByTarget)
      .map(
        ([targetId, notes]) =>
          [
            targetId,
            notes.filter((note) => !isAiGeneratedNote(note.content, note.username)),
          ] as const,
      )
      .filter(([, notes]) => notes.length > 0);

    return Object.fromEntries(entries) as Record<string, NoteEntryWithMetric[]>;
  }, [notesByTarget]);

  const sortedTargets = useMemo(
    () => Object.keys(visibleNotesByTarget).sort(compareTargets),
    [visibleNotesByTarget],
  );

  const totalChipNotes = useMemo(
    () => sortedTargets.reduce((sum, t) => sum + (visibleNotesByTarget[t]?.length ?? 0), 0),
    [sortedTargets, visibleNotesByTarget],
  );

  const sortedTaskNotes = useMemo(
    () =>
      taskNotes
        .filter((note) => !isAiGeneratedNote(note.content, note.username))
        .sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()),
    [taskNotes],
  );

  if (sortedTargets.length === 0 && sortedTaskNotes.length === 0) {
    return (
      <div className="text-sm text-base-content/60 italic flex items-center gap-2">
        <StickyNote className="h-4 w-4" />
        No notes yet. Click any cell on a metric below — or open a task result — to leave one.
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {/* Per-(target, metric) chip notes */}
      {sortedTargets.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-baseline gap-2">
            <h4 className="text-sm font-semibold">Per-metric notes</h4>
            <span className="text-xs text-base-content/60">
              {totalChipNotes} across {sortedTargets.length} target
              {sortedTargets.length > 1 ? "s" : ""} — click to open the metric.
            </span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {sortedTargets.map((targetId) => {
              const notes = [...(visibleNotesByTarget[targetId] ?? [])].sort((a, b) =>
                a.metricTitle.localeCompare(b.metricTitle),
              );
              return (
                <div
                  key={targetId}
                  className="rounded-lg border border-base-300 bg-base-200/40 p-3 space-y-2"
                >
                  <div className="flex items-center justify-between">
                    <h5 className="font-semibold text-sm">{formatTarget(targetId)}</h5>
                    <span className="badge badge-warning badge-sm">
                      {notes.length} note{notes.length > 1 ? "s" : ""}
                    </span>
                  </div>
                  <ul className="space-y-1.5">
                    {notes.map((n) => (
                      <li key={n.metricKey}>
                        <button
                          onClick={() => onEdit(n)}
                          className="w-full text-left rounded-md px-2 py-1.5 hover:bg-base-300/60 transition-colors border-l-2 border-warning/60"
                          title={`Open ${formatTarget(targetId)} · ${n.metricTitle}`}
                        >
                          <div className="flex items-center justify-between gap-2 text-xs">
                            <span className="font-semibold">{n.metricTitle}</span>
                            <span className="text-base-content/50 truncate">
                              {n.username} · {formatDate(n.updatedAt)}
                            </span>
                          </div>
                          <p className="text-xs text-base-content/80 line-clamp-2 break-words mt-0.5">
                            {n.content}
                          </p>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Per-task_result notes */}
      {sortedTaskNotes.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-baseline gap-2">
            <h4 className="text-sm font-semibold">Per-experiment notes</h4>
            <span className="text-xs text-base-content/60">
              {sortedTaskNotes.length} note
              {sortedTaskNotes.length > 1 ? "s" : ""} — opens the task result detail page.
            </span>
          </div>
          <ul className="space-y-2">
            {sortedTaskNotes.map((n) => (
              <li key={n.taskId} className="rounded-lg border border-base-300 bg-base-200/40">
                <Link
                  href={`/task-results/${n.taskId}`}
                  className="block px-3 py-2 hover:bg-base-300/40 transition-colors rounded-lg"
                  title={`Open task result ${n.taskId}`}
                >
                  <div className="flex items-center justify-between gap-2 text-xs">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="badge badge-sm badge-outline">
                        {n.qid ? `Q${n.qid}` : "—"}
                      </span>
                      <span className="font-mono text-base-content/60 truncate">{n.taskId}</span>
                    </div>
                    <span className="text-base-content/50 flex items-center gap-1 flex-shrink-0">
                      {n.username} · {formatDate(n.updatedAt)}
                      <ExternalLink className="h-3 w-3" />
                    </span>
                  </div>
                  <p className="text-xs text-base-content/80 line-clamp-2 break-words mt-1">
                    {n.content}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
