"use client";

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
  if (!isOpen) return null;

  return (
    <div className="modal modal-open">
      <div className="modal-box">
        <h3 className="font-bold text-lg">Cancel Execution</h3>
        <p className="py-4">
          Are you sure you want to cancel this execution? This action cannot be undone.
        </p>
        <div className="modal-action">
          <button className="btn btn-ghost" onClick={onClose} disabled={isPending}>
            Close
          </button>
          <button className="btn btn-error" onClick={onConfirm} disabled={isPending}>
            {isPending ? (
              <span className="loading loading-spinner loading-sm" />
            ) : (
              "Cancel Execution"
            )}
          </button>
        </div>
      </div>
      <div className="modal-backdrop" onClick={() => !isPending && onClose()} />
    </div>
  );
}
