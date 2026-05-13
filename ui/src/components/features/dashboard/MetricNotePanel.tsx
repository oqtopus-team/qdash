"use client";

import { useEffect, useState } from "react";

import { Pencil, Save, StickyNote, Trash2, X } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import {
  getGetChipNotesSummaryQueryKey,
  useDeleteCouplingMetricNote,
  useDeleteQubitMetricNote,
  useUpsertCouplingMetricNote,
  useUpsertQubitMetricNote,
} from "@/client/note/note";
import type { GetChipNotesSummaryParams } from "@/schemas";
import { MarkdownContent } from "@/components/ui/MarkdownContent";
import { MarkdownEditor, type MentionCandidate } from "@/components/ui/MarkdownEditor";
import { formatDateTime } from "@/lib/utils/datetime";

export interface NoteEntry {
  targetId: string;
  metricKey: string;
  content: string;
  username: string;
  updatedAt: string;
}

export interface NoteEntryWithMetric extends NoteEntry {
  metricTitle: string;
}

interface MetricNotePanelProps {
  chipId: string;
  /** "0" for a qubit, "0-1" for a coupling. */
  targetId: string;
  metricKey: string;
  metricTitle: string;
  /** Cooldown scope identifier used by the backend for metric notes. */
  cooldownId?: string | null;
  /** Optional human-readable label for the current cooldown/session. */
  cooldownLabel?: string | null;
  noteScopeParams?: GetChipNotesSummaryParams;
  existing?: NoteEntry;
  /** Notes on the same target on OTHER metrics, shown as read-only context. */
  otherNotes?: NoteEntryWithMetric[];
  mentionCandidates?: MentionCandidate[];
}

function formatTarget(targetId: string): string {
  if (targetId.includes("-")) {
    const [a, b] = targetId.split("-");
    return `Q${a} → Q${b}`;
  }
  return `Q${targetId}`;
}

/**
 * Inline panel for reading and editing the per-(target, metric) note
 * within the dashboard. Designed to sit alongside the metric history view
 * inside DashboardMetricModal — no overlay of its own.
 */
export function MetricNotePanel({
  chipId,
  targetId,
  metricKey,
  metricTitle,
  cooldownId,
  cooldownLabel,
  noteScopeParams,
  existing,
  otherNotes,
  mentionCandidates,
}: MetricNotePanelProps) {
  const queryClient = useQueryClient();
  const isCoupling = targetId.includes("-");

  const [mode, setMode] = useState<"view" | "edit">("view");
  const [draft, setDraft] = useState(existing?.content ?? "");

  const upsertQubit = useUpsertQubitMetricNote();
  const deleteQubit = useDeleteQubitMetricNote();
  const upsertCoupling = useUpsertCouplingMetricNote();
  const deleteCoupling = useDeleteCouplingMetricNote();
  const upsertPending = isCoupling ? upsertCoupling.isPending : upsertQubit.isPending;
  const deletePending = isCoupling ? deleteCoupling.isPending : deleteQubit.isPending;

  useEffect(() => {
    setDraft(existing?.content ?? "");
    setMode("view");
  }, [existing?.content, targetId, metricKey]);

  const invalidate = () =>
    queryClient.invalidateQueries({
      queryKey: getGetChipNotesSummaryQueryKey(chipId, noteScopeParams),
    });

  const handleSave = async () => {
    const trimmed = draft.trim();
    if (!trimmed || draft.length > 5000) {
      return;
    }
    if (isCoupling) {
      await upsertCoupling.mutateAsync({
        chipId,
        couplingId: targetId,
        metricKey,
        params: noteScopeParams,
        data: { content: draft },
      });
    } else {
      await upsertQubit.mutateAsync({
        chipId,
        qid: targetId,
        metricKey,
        params: noteScopeParams,
        data: { content: draft },
      });
    }
    await invalidate();
    setMode("view");
  };

  const handleDelete = async () => {
    if (!existing) {
      setDraft("");
      setMode("view");
      return;
    }
    if (isCoupling) {
      await deleteCoupling.mutateAsync({
        chipId,
        couplingId: targetId,
        metricKey,
        params: noteScopeParams,
      });
    } else {
      await deleteQubit.mutateAsync({
        chipId,
        qid: targetId,
        metricKey,
        params: noteScopeParams,
      });
    }
    await invalidate();
    setDraft("");
    setMode("view");
  };

  const handleCancel = () => {
    setDraft(existing?.content ?? "");
    setMode("view");
  };

  const scopeLabel = cooldownLabel
    ? `Current cooldown · ${cooldownLabel}`
    : cooldownId
      ? `Current cooldown · ${cooldownId}`
      : noteScopeParams?.start_at
        ? "Selected time range"
        : "Global note context";

  return (
    <aside
      className="flex flex-col bg-base-200/40 border-l border-base-300 lg:h-full overflow-hidden"
      aria-label="Metric note"
    >
      {/* Section header */}
      <div className="px-4 pt-4 pb-2 border-b border-base-300/70">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <StickyNote className="h-4 w-4 text-warning" />
          Metric note
        </div>
        <div className="mt-0.5 text-xs text-base-content/60">{scopeLabel}</div>
        <div className="mt-1 text-xs text-base-content/50">
          For {formatTarget(targetId)} · {metricTitle}. Saved to the active operational scope, not
          as a permanent chip-wide note.
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-auto p-4 space-y-3">
        {mode === "view" ? (
          <ViewState
            existing={existing}
            onEdit={() => setMode("edit")}
            onDelete={handleDelete}
            deletePending={deletePending}
          />
        ) : (
          <EditState
            existing={existing}
            draft={draft}
            onChange={setDraft}
            onSave={handleSave}
            onCancel={handleCancel}
            onDelete={handleDelete}
            upsertPending={upsertPending}
            deletePending={deletePending}
            mentionCandidates={mentionCandidates}
          />
        )}

        {otherNotes && otherNotes.length > 0 && (
          <details className="rounded-md bg-base-100 border border-base-300">
            <summary className="px-3 py-2 cursor-pointer text-xs font-semibold flex items-center justify-between">
              <span>
                Other notes for {formatTarget(targetId)}
                <span className="ml-1 text-base-content/60 font-normal">({otherNotes.length})</span>
              </span>
              <span className="text-base-content/40 font-normal">read-only</span>
            </summary>
            <ul className="px-3 pb-3 pt-1 space-y-2 text-xs">
              {otherNotes.map((note) => (
                <li key={note.metricKey} className="border-l-2 border-base-300 pl-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold">{note.metricTitle}</span>
                    <span className="text-base-content/50">
                      {note.username} · {formatDateTime(note.updatedAt)}
                    </span>
                  </div>
                  <div className="mt-1 text-base-content/80">
                    <MarkdownContent content={note.content} />
                  </div>
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </aside>
  );
}

function ViewState({
  existing,
  onEdit,
  onDelete,
  deletePending,
}: {
  existing?: NoteEntry;
  onEdit: () => void;
  onDelete: () => void;
  deletePending: boolean;
}) {
  if (!existing || !existing.content.trim()) {
    return (
      <div className="rounded-lg border border-dashed border-base-300 p-4 text-center space-y-3 bg-base-100">
        <div className="flex justify-center text-base-content/40">
          <StickyNote className="h-7 w-7" />
        </div>
        <div className="text-sm text-base-content/70">
          No note for this metric on the current view yet.
        </div>
        <button className="btn btn-sm btn-primary gap-1" onClick={onEdit} type="button">
          <Pencil className="h-3.5 w-3.5" />
          Add note
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="rounded-md bg-base-100 border border-base-300 p-3">
        <MarkdownContent content={existing.content} />
      </div>
      <div className="text-[11px] text-base-content/60 flex flex-wrap gap-x-2">
        <span>
          Last edited by{" "}
          <span className="font-medium text-base-content/80">{existing.username || "—"}</span>
        </span>
        {existing.updatedAt && <span>· {formatDateTime(existing.updatedAt)}</span>}
      </div>
      <div className="flex gap-2 pt-1">
        <button className="btn btn-sm btn-primary gap-1" onClick={onEdit} type="button">
          <Pencil className="h-3.5 w-3.5" />
          Edit
        </button>
        <button
          className="btn btn-sm btn-ghost text-error gap-1"
          onClick={onDelete}
          disabled={deletePending}
          type="button"
        >
          <Trash2 className="h-3.5 w-3.5" />
          {deletePending ? "Deleting…" : "Delete"}
        </button>
      </div>
    </div>
  );
}

function EditState({
  existing,
  draft,
  onChange,
  onSave,
  onCancel,
  onDelete,
  upsertPending,
  deletePending,
  mentionCandidates,
}: {
  existing?: NoteEntry;
  draft: string;
  onChange: (v: string) => void;
  onSave: () => void;
  onCancel: () => void;
  onDelete: () => void;
  upsertPending: boolean;
  deletePending: boolean;
  mentionCandidates?: MentionCandidate[];
}) {
  const trimmed = draft.trim();
  const isTooLong = draft.length > 5000;
  return (
    <div className="space-y-2">
      <MarkdownEditor
        value={draft}
        onChange={onChange}
        onSubmit={onSave}
        placeholder="Calibration quirks, anomalies, or context for this metric on the current cooldown…"
        rows={8}
        disabled={upsertPending}
        mentionCandidates={mentionCandidates}
      />
      <div className="flex items-center justify-between text-[11px] text-base-content/50">
        <span className={isTooLong ? "text-error" : undefined}>{draft.length} / 5000</span>
        {existing?.updatedAt && (
          <span>
            Last edited {formatDateTime(existing.updatedAt)} by {existing.username || "—"}
          </span>
        )}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
        <button
          className="btn btn-sm btn-ghost text-error gap-1"
          onClick={onDelete}
          disabled={!existing || deletePending}
          type="button"
          title={existing ? "Delete this note" : "No saved note to delete"}
        >
          <Trash2 className="h-3.5 w-3.5" />
          Delete
        </button>
        <div className="flex gap-2 ml-auto">
          <button className="btn btn-sm btn-ghost gap-1" onClick={onCancel} type="button">
            <X className="h-3.5 w-3.5" />
            Cancel
          </button>
          <button
            className="btn btn-sm btn-primary gap-1"
            onClick={onSave}
            disabled={upsertPending || !trimmed || isTooLong}
            type="button"
          >
            <Save className="h-3.5 w-3.5" />
            {upsertPending ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}
