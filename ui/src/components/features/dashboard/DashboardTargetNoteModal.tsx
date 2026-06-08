"use client";

import { useEffect, useState } from "react";

import { Pencil, Save, StickyNote, Trash2, X } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import {
  getGetChipNotesSummaryQueryKey,
  useDeleteCouplingNote,
  useDeleteQubitNote,
  useUpsertCouplingNote,
  useUpsertQubitNote,
} from "@/client/note/note";
import { MarkdownContent } from "@/components/ui/MarkdownContent";
import { MarkdownEditor, type MentionCandidate } from "@/components/ui/MarkdownEditor";
import { formatDateTime } from "@/lib/utils/datetime";
import type { GetChipNotesSummaryParams } from "@/schemas";

export interface TargetNoteEntry {
  targetId: string;
  content: string;
  username: string;
  updatedAt: string;
}

interface DashboardTargetNoteModalProps {
  chipId: string;
  targetId: string;
  noteScopeParams?: GetChipNotesSummaryParams;
  existing?: TargetNoteEntry;
  mentionCandidates?: MentionCandidate[];
  onClose: () => void;
}

function formatTarget(targetId: string): string {
  if (targetId.includes("-")) {
    const [a, b] = targetId.split("-");
    return `Q${a} -> Q${b}`;
  }
  return `Q${targetId}`;
}

export function DashboardTargetNoteModal({
  chipId,
  targetId,
  noteScopeParams,
  existing,
  mentionCandidates,
  onClose,
}: DashboardTargetNoteModalProps) {
  const queryClient = useQueryClient();
  const isCoupling = targetId.includes("-");
  const upsertQubit = useUpsertQubitNote();
  const deleteQubit = useDeleteQubitNote();
  const upsertCoupling = useUpsertCouplingNote();
  const deleteCoupling = useDeleteCouplingNote();
  const upsertPending = isCoupling ? upsertCoupling.isPending : upsertQubit.isPending;
  const deletePending = isCoupling ? deleteCoupling.isPending : deleteQubit.isPending;

  const [mode, setMode] = useState<"view" | "edit">(existing ? "view" : "edit");
  const [draft, setDraft] = useState(existing?.content ?? "");

  useEffect(() => {
    setDraft(existing?.content ?? "");
    setMode(existing ? "view" : "edit");
  }, [existing, targetId]);

  const invalidate = () =>
    queryClient.invalidateQueries({
      queryKey: getGetChipNotesSummaryQueryKey(chipId, noteScopeParams),
    });

  const handleSave = async () => {
    if (!draft.trim() || draft.length > 5000) return;
    if (isCoupling) {
      await upsertCoupling.mutateAsync({
        chipId,
        couplingId: targetId,
        data: { content: draft },
      });
    } else {
      await upsertQubit.mutateAsync({
        chipId,
        qid: targetId,
        data: { content: draft },
      });
    }
    await invalidate();
    onClose();
  };

  const handleDelete = async () => {
    if (!existing) {
      setDraft("");
      onClose();
      return;
    }
    if (isCoupling) {
      await deleteCoupling.mutateAsync({ chipId, couplingId: targetId });
    } else {
      await deleteQubit.mutateAsync({ chipId, qid: targetId });
    }
    await invalidate();
    onClose();
  };

  const isTooLong = draft.length > 5000;

  return (
    <div
      className="modal modal-open"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal-box w-full max-w-2xl p-0 overflow-hidden">
        <div className="px-5 py-4 border-b border-base-300 flex items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-lg font-bold">
              <StickyNote className="h-5 w-5 text-warning" />
              <span className="truncate">Target note · {formatTarget(targetId)}</span>
            </div>
            <p className="text-sm text-base-content/60 mt-1">
              Permanent target-level context, available even when this metric has no data.
            </p>
          </div>
          <button
            className="btn btn-ghost btn-sm btn-circle"
            onClick={onClose}
            type="button"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="p-5 space-y-4">
          {mode === "view" && existing ? (
            <div className="space-y-3">
              <div className="rounded-md bg-base-100 border border-base-300 p-3">
                <MarkdownContent content={existing.content} />
              </div>
              <div className="text-[11px] text-base-content/60 flex flex-wrap gap-x-2">
                <span>
                  Last edited by{" "}
                  <span className="font-medium text-base-content/80">
                    {existing.username || "-"}
                  </span>
                </span>
                {existing.updatedAt && <span>· {formatDateTime(existing.updatedAt)}</span>}
              </div>
              <div className="flex gap-2">
                <button
                  className="btn btn-sm btn-primary gap-1"
                  onClick={() => setMode("edit")}
                  type="button"
                >
                  <Pencil className="h-3.5 w-3.5" />
                  Edit
                </button>
                <button
                  className="btn btn-sm btn-ghost text-error gap-1"
                  onClick={handleDelete}
                  disabled={deletePending}
                  type="button"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  {deletePending ? "Deleting..." : "Delete"}
                </button>
              </div>
            </div>
          ) : (
            <>
              <MarkdownEditor
                value={draft}
                onChange={setDraft}
                onSubmit={handleSave}
                placeholder="Target-level caveats, missing-data reasons, wiring notes, or follow-up context..."
                rows={8}
                disabled={upsertPending}
                mentionCandidates={mentionCandidates}
              />
              <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-base-content/50">
                <span className={isTooLong ? "text-error" : undefined}>{draft.length} / 5000</span>
                {existing?.updatedAt && (
                  <span>
                    Last edited {formatDateTime(existing.updatedAt)} by {existing.username || "-"}
                  </span>
                )}
              </div>
            </>
          )}
        </div>

        {mode === "edit" && (
          <div className="px-5 py-4 border-t border-base-300 flex flex-wrap justify-between gap-2">
            <button
              className="btn btn-sm btn-ghost text-error gap-1"
              onClick={handleDelete}
              disabled={!existing || deletePending}
              type="button"
            >
              <Trash2 className="h-3.5 w-3.5" />
              {deletePending ? "Deleting..." : "Delete"}
            </button>
            <div className="flex gap-2">
              <button className="btn btn-sm btn-ghost" onClick={onClose} type="button">
                Cancel
              </button>
              <button
                className="btn btn-sm btn-primary gap-1"
                onClick={handleSave}
                disabled={!draft.trim() || isTooLong || upsertPending}
                type="button"
              >
                <Save className="h-4 w-4" />
                {upsertPending ? "Saving..." : "Save note"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
