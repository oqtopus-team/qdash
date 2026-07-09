"use client";

import { useEffect, useState } from "react";

import { Pencil, Save, StickyNote, X } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import {
  getGetChipNoteQueryKey,
  getGetChipQueryKey,
  getListChipsQueryKey,
  useDeleteChipNote,
  useGetChipNote,
  useUpsertChipNote,
} from "@/client/chip/chip";
import type { GetChipNoteParams } from "@/schemas";
import { MarkdownContent } from "@/components/ui/MarkdownContent";
import { MarkdownEditor } from "@/components/ui/MarkdownEditor";
import { formatDateTime } from "@/lib/utils/datetime";

interface DashboardChipNoteCardProps {
  chipId: string;
  noteScopeParams?: GetChipNoteParams;
}

export function DashboardChipNoteCard({ chipId, noteScopeParams }: DashboardChipNoteCardProps) {
  const queryClient = useQueryClient();
  const { data: noteData, isLoading } = useGetChipNote(chipId, noteScopeParams);
  const upsertChipNote = useUpsertChipNote();
  const deleteChipNote = useDeleteChipNote();
  const note = noteData?.data;
  const hasNote = Boolean(note?.content?.trim());
  const isPending = upsertChipNote.isPending || deleteChipNote.isPending;
  const [mode, setMode] = useState<"view" | "edit">("view");
  const [draft, setDraft] = useState("");

  useEffect(() => {
    setDraft(note?.content ?? "");
    setMode(note?.content?.trim() ? "view" : "edit");
  }, [
    note?.content,
    chipId,
    noteScopeParams?.cooldown_id,
    noteScopeParams?.start_at,
    noteScopeParams?.end_at,
  ]);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: getGetChipNoteQueryKey(chipId, noteScopeParams) });
    queryClient.invalidateQueries({ queryKey: getListChipsQueryKey() });
    queryClient.invalidateQueries({ queryKey: getGetChipQueryKey(chipId) });
  };

  const handleSave = async () => {
    if (draft.trim()) {
      await upsertChipNote.mutateAsync({
        chipId,
        data: { content: draft },
        params: noteScopeParams,
      });
    } else if (hasNote) {
      await deleteChipNote.mutateAsync({ chipId, params: noteScopeParams });
    } else {
      return;
    }
    invalidate();
    setMode(draft.trim() ? "view" : "edit");
  };

  const handleCancel = () => {
    setDraft(note?.content ?? "");
    setMode(note?.content?.trim() ? "view" : "edit");
  };

  return (
    <section className="rounded-lg border border-base-300 bg-base-100 overflow-hidden">
      <div className="px-4 py-3 border-b border-base-300 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <StickyNote className="h-4 w-4 text-warning" />
            Chip note · {chipId}
          </div>
          <div className="mt-0.5 text-xs text-base-content/60">
            Chip-level context for the selected cooldown.
          </div>
        </div>
        {mode === "view" && (
          <button
            className="btn btn-sm btn-outline gap-1"
            onClick={() => setMode("edit")}
            type="button"
            disabled={isLoading}
          >
            <Pencil className="h-3.5 w-3.5" />
            Edit
          </button>
        )}
      </div>

      <div className="p-4 space-y-3">
        {isLoading ? (
          <div className="text-sm text-base-content/60">Loading...</div>
        ) : mode === "view" && hasNote ? (
          <>
            <div className="rounded-md bg-base-100 border border-base-300 p-3">
              <MarkdownContent content={note?.content ?? ""} />
            </div>
            <div className="text-[11px] text-base-content/60 flex flex-wrap gap-x-2">
              {note?.updated_by && <span>Last edited by {note.updated_by}</span>}
              {note?.updated_at && <span>· {formatDateTime(note.updated_at)}</span>}
            </div>
          </>
        ) : (
          <>
            <MarkdownEditor
              value={draft}
              onChange={setDraft}
              onSubmit={handleSave}
              placeholder="Write a summary of this chip here."
              rows={6}
              disabled={isPending}
            />
            <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-base-content/50">
              <span>{draft.length} characters</span>
              {note?.updated_by && (
                <span>
                  Last edited by {note.updated_by}
                  {note.updated_at && <> · {formatDateTime(note.updated_at)}</>}
                </span>
              )}
            </div>
            <div className="flex justify-end gap-2">
              {hasNote && (
                <button className="btn btn-sm btn-ghost gap-1" onClick={handleCancel} type="button">
                  <X className="h-3.5 w-3.5" />
                  Cancel
                </button>
              )}
              <button
                className="btn btn-sm btn-primary gap-1"
                onClick={handleSave}
                disabled={isPending || (!draft.trim() && !hasNote)}
                type="button"
              >
                <Save className="h-3.5 w-3.5" />
                {isPending ? "Saving..." : draft.trim() ? "Save note" : "Clear note"}
              </button>
            </div>
          </>
        )}
      </div>
    </section>
  );
}
