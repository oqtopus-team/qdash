"use client";

import { useEffect, useState } from "react";

import { AlertTriangle, Save, Trash2, X } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import {
  getGetChipDeletionImpactQueryOptions,
  getGetChipQueryKey,
  getListChipsQueryKey,
  useDeleteChip,
  useGetChip,
  useGetChipDeletionImpact,
  useUpdateChip,
} from "@/client/chip/chip";
import { formatDateTime } from "@/lib/utils/datetime";

interface ChipManageModalProps {
  chipId: string;
  onClose: () => void;
  /** Called after a successful delete — caller should clear the selected chip. */
  onDeleted?: () => void;
}

export function ChipManageModal({
  chipId,
  onClose,
  onDeleted,
}: ChipManageModalProps) {
  const queryClient = useQueryClient();
  const { data: chipData } = useGetChip(chipId);
  const { data: impactData, refetch: refetchImpact } =
    useGetChipDeletionImpact(chipId);
  const updateChip = useUpdateChip();
  const deleteChip = useDeleteChip();

  const chip = chipData?.data;
  const impact = impactData?.data;

  const [topologyId, setTopologyId] = useState("");
  const [note, setNote] = useState("");
  const [forceDelete, setForceDelete] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    if (chip) {
      setTopologyId(chip.topology_id ?? "");
      setNote(chip.note?.content ?? "");
    }
  }, [chip]);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: getListChipsQueryKey() });
    queryClient.invalidateQueries({ queryKey: getGetChipQueryKey(chipId) });
    queryClient.invalidateQueries({
      queryKey: getGetChipDeletionImpactQueryOptions(chipId).queryKey,
    });
  };

  const handleSave = async () => {
    await updateChip.mutateAsync({
      chipId,
      data: {
        topology_id: topologyId || null,
        note,
      },
    });
    invalidate();
  };

  const handleDelete = async () => {
    if (!confirmDelete) {
      setConfirmDelete(true);
      await refetchImpact();
      return;
    }
    await deleteChip.mutateAsync({
      chipId,
      params: { force: forceDelete },
    });
    invalidate();
    onDeleted?.();
    onClose();
  };

  return (
    <div
      className="modal modal-open"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal-box w-full max-w-2xl">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold">Manage chip · {chipId}</h3>
          <button className="btn btn-ghost btn-sm btn-square" onClick={onClose}>
            <X className="h-4 w-4" />
          </button>
        </div>

        {!chip ? (
          <div className="text-base-content/60 text-sm">Loading…</div>
        ) : (
          <div className="space-y-5">
            {/* Read-only meta */}
            <div className="text-xs text-base-content/60 grid grid-cols-2 gap-2">
              <div>
                <span className="opacity-60">Size:</span> {chip.size} qubits
              </div>
              <div>
                <span className="opacity-60">Installed:</span>{" "}
                {formatDateTime(chip.installed_at)}
              </div>
              <div className="col-span-2">
                <span className="opacity-60">Current cool-down:</span>{" "}
                {chip.current_cooldown_id ?? (
                  <span className="italic text-base-content/40">none</span>
                )}
              </div>
            </div>

            {/* Edit form */}
            <div className="space-y-3">
              <Field label="Topology ID">
                <input
                  className="input input-sm input-bordered w-full"
                  value={topologyId}
                  onChange={(e) => setTopologyId(e.target.value)}
                  placeholder={`square-lattice-mux-${chip.size}`}
                />
                <p className="text-[11px] text-base-content/50 mt-1">
                  Topology template applied to qubit/coupling layout.
                </p>
              </Field>
              <Field label="Note">
                <textarea
                  className="textarea textarea-bordered w-full text-sm"
                  rows={3}
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="Serial number, fabrication batch, design doc link…"
                />
                {chip.note?.updated_by && (
                  <p className="text-[11px] text-base-content/50 mt-1">
                    Last edited by {chip.note.updated_by}
                    {chip.note.updated_at && (
                      <>
                        {" · "}
                        {formatDateTime(chip.note.updated_at)}
                      </>
                    )}
                  </p>
                )}
              </Field>
              <div className="flex justify-end">
                <button
                  className="btn btn-sm btn-primary gap-1"
                  onClick={handleSave}
                  disabled={updateChip.isPending}
                >
                  <Save className="h-4 w-4" />
                  {updateChip.isPending ? "Saving…" : "Save changes"}
                </button>
              </div>
            </div>

            {/* Danger zone */}
            <div className="rounded-lg border border-error/40 bg-error/5 p-3 space-y-3">
              <div className="flex items-center gap-2 text-sm font-semibold text-error">
                <AlertTriangle className="h-4 w-4" />
                Danger zone
              </div>

              {impact && (
                <div className="text-xs space-y-1">
                  <div>
                    <span className="font-semibold">Hard-deleted:</span>{" "}
                    {impact.qubits} qubit{impact.qubits !== 1 ? "s" : ""},{" "}
                    {impact.couplings} coupling
                    {impact.couplings !== 1 ? "s" : ""}
                  </div>
                  <div className="text-base-content/60">
                    <span className="font-semibold">Retained for audit:</span>{" "}
                    {impact.task_results} task result
                    {impact.task_results !== 1 ? "s" : ""},{" "}
                    {impact.qubit_history_snapshots} qubit snapshot
                    {impact.qubit_history_snapshots !== 1 ? "s" : ""},{" "}
                    {impact.coupling_history_snapshots} coupling snapshot
                    {impact.coupling_history_snapshots !== 1 ? "s" : ""}
                  </div>
                  {impact.cooldowns_referencing > 0 && (
                    <div>
                      <span className="font-semibold">Detached from:</span>{" "}
                      {impact.cooldowns_referencing} cool-down
                      {impact.cooldowns_referencing !== 1 ? "s" : ""}
                    </div>
                  )}
                  {!impact.can_delete_safely && (
                    <label className="flex items-center gap-2 mt-1 cursor-pointer">
                      <input
                        type="checkbox"
                        className="checkbox checkbox-sm checkbox-error"
                        checked={forceDelete}
                        onChange={(e) => setForceDelete(e.target.checked)}
                      />
                      <span>
                        I understand this will cascade-delete the chip&apos;s
                        qubits and couplings.
                      </span>
                    </label>
                  )}
                </div>
              )}

              <div className="flex justify-end gap-2">
                {confirmDelete && (
                  <button
                    className="btn btn-sm btn-ghost"
                    onClick={() => {
                      setConfirmDelete(false);
                      setForceDelete(false);
                    }}
                  >
                    Cancel
                  </button>
                )}
                <button
                  className="btn btn-sm btn-error gap-1"
                  onClick={handleDelete}
                  disabled={
                    deleteChip.isPending ||
                    (confirmDelete &&
                      impact !== undefined &&
                      !impact.can_delete_safely &&
                      !forceDelete)
                  }
                >
                  <Trash2 className="h-4 w-4" />
                  {deleteChip.isPending
                    ? "Deleting…"
                    : confirmDelete
                      ? "Confirm delete"
                      : "Delete chip"}
                </button>
              </div>
              {deleteChip.error && (
                <div className="text-xs text-error mt-1">
                  {extractErrorMessage(deleteChip.error)}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="block text-xs text-base-content/60 mb-1">{label}</label>
      {children}
    </div>
  );
}

function extractErrorMessage(err: unknown): string {
  if (
    err &&
    typeof err === "object" &&
    "response" in err &&
    err.response &&
    typeof err.response === "object" &&
    "data" in err.response
  ) {
    const data = (err.response as { data?: unknown }).data;
    if (data && typeof data === "object" && "detail" in data) {
      const detail = (data as { detail?: unknown }).detail;
      if (typeof detail === "string") return detail;
    }
  }
  if (err instanceof Error) return err.message;
  return "Failed to delete chip.";
}
