"use client";

import { useEffect, useState } from "react";

import { Save, Trash2, X } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import {
  getGetChipNotesSummaryQueryKey,
  useDeleteCouplingMetricNote,
  useDeleteQubitMetricNote,
  useUpsertCouplingMetricNote,
  useUpsertQubitMetricNote,
} from "@/client/note/note";
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

interface ChipNoteEditorProps {
  chipId: string;
  /** "0" for a qubit, "0-1" for a coupling. */
  targetId: string;
  metricKey: string;
  metricTitle: string;
  existing?: NoteEntry;
  /** Notes on the same target on OTHER metrics, shown as read-only context. */
  otherNotes?: NoteEntryWithMetric[];
  onClose: () => void;
}

function formatTarget(targetId: string): string {
  if (targetId.includes("-")) {
    const [a, b] = targetId.split("-");
    return `Q${a} → Q${b}`;
  }
  return `Q${targetId}`;
}

export function ChipNoteEditor({
  chipId,
  targetId,
  metricKey,
  metricTitle,
  existing,
  otherNotes,
  onClose,
}: ChipNoteEditorProps) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState(existing?.content ?? "");
  const isCoupling = targetId.includes("-");
  const upsertQubit = useUpsertQubitMetricNote();
  const deleteQubit = useDeleteQubitMetricNote();
  const upsertCoupling = useUpsertCouplingMetricNote();
  const deleteCoupling = useDeleteCouplingMetricNote();
  const upsertPending = isCoupling
    ? upsertCoupling.isPending
    : upsertQubit.isPending;
  const deletePending = isCoupling
    ? deleteCoupling.isPending
    : deleteQubit.isPending;

  useEffect(() => {
    setDraft(existing?.content ?? "");
  }, [existing?.content]);

  const invalidate = () =>
    queryClient.invalidateQueries({
      queryKey: getGetChipNotesSummaryQueryKey(chipId),
    });

  const handleSave = async () => {
    if (isCoupling) {
      await upsertCoupling.mutateAsync({
        chipId,
        couplingId: targetId,
        metricKey,
        data: { content: draft },
      });
    } else {
      await upsertQubit.mutateAsync({
        chipId,
        qid: targetId,
        metricKey,
        data: { content: draft },
      });
    }
    await invalidate();
    onClose();
  };

  const handleDelete = async () => {
    if (!existing) {
      onClose();
      return;
    }
    if (isCoupling) {
      await deleteCoupling.mutateAsync({
        chipId,
        couplingId: targetId,
        metricKey,
      });
    } else {
      await deleteQubit.mutateAsync({
        chipId,
        qid: targetId,
        metricKey,
      });
    }
    await invalidate();
    onClose();
  };

  return (
    <div
      className="fixed inset-0 z-[1100] flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      onClick={onClose}
    >
      <div
        className="bg-base-100 rounded-xl shadow-2xl w-full max-w-lg p-5 space-y-3"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-bold">
            Note · {formatTarget(targetId)} · {metricTitle}
            {existing && (
              <span className="ml-2 text-xs font-normal text-base-content/60">
                last edit by {existing.username}
              </span>
            )}
          </h3>
          <button
            className="btn btn-ghost btn-sm btn-square"
            onClick={onClose}
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <textarea
          className="textarea textarea-bordered w-full h-40 text-sm"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={`Note for ${formatTarget(targetId)} on ${metricTitle} (calibration quirks, anomalies, etc.)`}
          maxLength={5000}
          autoFocus
        />

        {otherNotes && otherNotes.length > 0 && (
          <details className="rounded-md bg-base-200/60 border border-base-300">
            <summary className="px-3 py-2 cursor-pointer text-xs font-semibold flex items-center justify-between">
              <span>
                Other notes for {formatTarget(targetId)}
                <span className="ml-1 text-base-content/60 font-normal">
                  ({otherNotes.length})
                </span>
              </span>
              <span className="text-base-content/40">click to expand</span>
            </summary>
            <ul className="px-3 pb-3 pt-1 space-y-2 text-xs">
              {otherNotes.map((note) => (
                <li
                  key={note.metricKey}
                  className="border-l-2 border-warning/60 pl-2"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold">{note.metricTitle}</span>
                    <span className="text-base-content/50">
                      {note.username} · {formatDateTime(note.updatedAt)}
                    </span>
                  </div>
                  <p className="whitespace-pre-wrap break-words text-base-content/80">
                    {note.content}
                  </p>
                </li>
              ))}
            </ul>
          </details>
        )}

        <div className="flex items-center justify-between">
          <button
            className="btn btn-sm btn-ghost text-error"
            onClick={handleDelete}
            disabled={!existing || deletePending}
            title={existing ? "Delete this note" : "No note to delete"}
          >
            <Trash2 className="h-4 w-4" />
            Delete
          </button>
          <div className="flex gap-2">
            <button className="btn btn-sm btn-ghost" onClick={onClose}>
              Cancel
            </button>
            <button
              className="btn btn-sm btn-primary"
              onClick={handleSave}
              disabled={upsertPending}
            >
              <Save className="h-4 w-4" />
              {upsertPending ? "Saving…" : "Save"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
