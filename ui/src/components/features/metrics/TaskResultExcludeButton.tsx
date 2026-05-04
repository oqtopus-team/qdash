"use client";

import React, { useState, useEffect, useRef } from "react";
import { Ban, RotateCcw } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useSetTaskResultExcluded } from "@/client/task-result/task-result";
import { formatDateTime } from "@/lib/utils/datetime";
import { isChipMetricsQuery } from "@/lib/utils/queryInvalidation";

interface TaskResultExcludeButtonProps {
  taskId: string;
  excluded: boolean;
  excludedReason?: string;
  excludedBy?: string | null;
  excludedAt?: string | null;
}

export function TaskResultExcludeButton({
  taskId,
  excluded,
  excludedReason,
  excludedBy,
  excludedAt,
}: TaskResultExcludeButtonProps) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState(excludedReason ?? "");
  const dialogRef = useRef<HTMLDialogElement>(null);
  const queryClient = useQueryClient();
  const mutation = useSetTaskResultExcluded();

  useEffect(() => {
    setReason(excludedReason ?? "");
  }, [excludedReason, taskId]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  const invalidateMetrics = async () => {
    await queryClient.invalidateQueries({ predicate: isChipMetricsQuery });
  };

  const handleExclude = async () => {
    await mutation.mutateAsync({
      taskId,
      data: { excluded: true, reason: reason.trim() },
    });
    await invalidateMetrics();
    setOpen(false);
  };

  const handleRestore = async () => {
    await mutation.mutateAsync({
      taskId,
      data: { excluded: false, reason: "" },
    });
    await invalidateMetrics();
  };

  if (excluded) {
    return (
      <div className="flex flex-col gap-1 p-2 rounded-md bg-warning/10 border border-warning/40">
        <div className="flex items-center justify-between gap-2">
          <span className="badge badge-warning badge-sm gap-1">
            <Ban className="h-3 w-3" />
            Excluded from metrics
          </span>
          <button
            type="button"
            onClick={handleRestore}
            disabled={mutation.isPending}
            className="btn btn-xs btn-ghost gap-1"
          >
            <RotateCcw className="h-3 w-3" />
            Restore
          </button>
        </div>
        {(excludedReason || excludedBy || excludedAt) && (
          <div className="text-[0.7rem] text-base-content/70 space-y-0.5">
            {excludedReason && <div>Reason: {excludedReason}</div>}
            {(excludedBy || excludedAt) && (
              <div>
                {excludedBy && <span>by {excludedBy}</span>}
                {excludedBy && excludedAt && <span> · </span>}
                {excludedAt && <span>{formatDateTime(excludedAt)}</span>}
              </div>
            )}
          </div>
        )}
      </div>
    );
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="btn btn-xs btn-outline btn-warning gap-1"
        disabled={mutation.isPending}
      >
        <Ban className="h-3 w-3" />
        Exclude this measurement
      </button>
      <dialog ref={dialogRef} className="modal" onClose={() => setOpen(false)}>
        <div className="modal-box">
          <h3 className="font-bold text-base mb-2">Exclude this measurement</h3>
          <p className="text-sm text-base-content/70 mb-3">
            Excluded measurements are skipped on the dashboard and metrics
            screens. Raw data is preserved and you can restore it later.
          </p>
          <label className="label">
            <span className="label-text text-sm">Reason (optional)</span>
          </label>
          <textarea
            className="textarea textarea-bordered w-full"
            rows={3}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="e.g. Bad fit / known cable issue"
          />
          <div className="modal-action">
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => setOpen(false)}
              disabled={mutation.isPending}
            >
              Cancel
            </button>
            <button
              type="button"
              className="btn btn-warning"
              onClick={handleExclude}
              disabled={mutation.isPending}
            >
              {mutation.isPending ? (
                <span className="loading loading-spinner loading-xs"></span>
              ) : (
                <Ban className="h-4 w-4" />
              )}
              Exclude
            </button>
          </div>
        </div>
        <form method="dialog" className="modal-backdrop">
          <button>close</button>
        </form>
      </dialog>
    </>
  );
}
