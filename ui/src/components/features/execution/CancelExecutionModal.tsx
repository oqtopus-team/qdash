"use client";

import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/Dialog";

export interface CancelExecutionModalProps {
  isOpen: boolean;
  isPending: boolean;
  onConfirm: () => void;
  onClose: () => void;
}

export function CancelExecutionModal({
  isOpen,
  isPending,
  onConfirm,
  onClose,
}: CancelExecutionModalProps) {
  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && !isPending && onClose()}>
      <DialogContent>
        <DialogTitle>Cancel Execution</DialogTitle>
        <DialogDescription className="py-4">
          Are you sure you want to cancel this execution? This action cannot be undone.
        </DialogDescription>
        <div className="modal-action">
          <button type="button" className="btn btn-ghost" onClick={onClose} disabled={isPending}>
            Close
          </button>
          <button type="button" className="btn btn-error" onClick={onConfirm} disabled={isPending}>
            {isPending ? (
              <span className="loading loading-spinner loading-sm" />
            ) : (
              "Cancel Execution"
            )}
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
