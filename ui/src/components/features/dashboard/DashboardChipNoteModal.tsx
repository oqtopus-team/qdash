"use client";

import { useEffect, useState } from "react";

import { Save, StickyNote, X } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import {
  getGetChipQueryKey,
  getListChipsQueryKey,
  useGetChip,
  useUpdateChip,
} from "@/client/chip/chip";
import { MarkdownEditor } from "@/components/ui/MarkdownEditor";
import { formatDateTime } from "@/lib/utils/datetime";

interface DashboardChipNoteModalProps {
  chipId: string;
  onClose: () => void;
}

export function DashboardChipNoteModal({
  chipId,
  onClose,
}: DashboardChipNoteModalProps) {
  const queryClient = useQueryClient();
  const { data: chipData } = useGetChip(chipId);
  const updateChip = useUpdateChip();
  const chip = chipData?.data;
  const [draft, setDraft] = useState("");

  useEffect(() => {
    setDraft(chip?.note?.content ?? "");
  }, [chip?.note?.content]);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: getListChipsQueryKey() });
    queryClient.invalidateQueries({ queryKey: getGetChipQueryKey(chipId) });
  };

  const handleSave = async () => {
    await updateChip.mutateAsync({
      chipId,
      data: { note: draft },
    });
    invalidate();
    onClose();
  };

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
              <span className="truncate">Chip note · {chipId}</span>
            </div>
            <p className="text-sm text-base-content/60 mt-1">
              Permanent chip-level context, separate from cooldown metric notes.
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
          {!chip ? (
            <div className="text-sm text-base-content/60">Loading…</div>
          ) : (
            <>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs text-base-content/60">
                <div>
                  <span className="opacity-60">Size:</span> {chip.size} qubits
                </div>
                <div>
                  <span className="opacity-60">Topology:</span>{" "}
                  {chip.topology_id ?? "default"}
                </div>
                <div>
                  <span className="opacity-60">Cooldown:</span>{" "}
                  {chip.current_cooldown_id ?? "none"}
                </div>
              </div>

              <MarkdownEditor
                value={draft}
                onChange={setDraft}
                onSubmit={handleSave}
                placeholder="Serial number, fabrication batch, shared caveats, design doc link…"
                rows={8}
                disabled={updateChip.isPending}
              />

              <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-base-content/50">
                <span>{draft.length} characters</span>
                {chip.note?.updated_by && (
                  <span>
                    Last edited by {chip.note.updated_by}
                    {chip.note.updated_at && (
                      <> · {formatDateTime(chip.note.updated_at)}</>
                    )}
                  </span>
                )}
              </div>
            </>
          )}
        </div>

        <div className="px-5 py-4 border-t border-base-300 flex justify-end gap-2">
          <button
            className="btn btn-sm btn-ghost"
            onClick={onClose}
            type="button"
          >
            Cancel
          </button>
          <button
            className="btn btn-sm btn-primary gap-1"
            onClick={handleSave}
            disabled={!chip || updateChip.isPending}
            type="button"
          >
            <Save className="h-4 w-4" />
            {updateChip.isPending ? "Saving…" : "Save note"}
          </button>
        </div>
      </div>
    </div>
  );
}
