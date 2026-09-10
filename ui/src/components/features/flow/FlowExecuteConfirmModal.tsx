"use client";

import { useId } from "react";

import { Plus } from "lucide-react";

interface FlowExecuteConfirmModalProps {
  flowName: string;
  username: string;
  chipId: string;
  description: string;
  tags: string;
  disabledReason: string | null;
  onConfirm: () => void;
  onClose: () => void;
}

export function FlowExecuteConfirmModal({
  flowName,
  username,
  chipId,
  description,
  tags,
  disabledReason,
  onConfirm,
  onClose,
}: FlowExecuteConfirmModalProps) {
  const disabledReasonId = useId();
  const tagList = tags
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean);

  return (
    <div
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="bg-base-100 rounded-xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-6 py-4 border-b border-base-300 flex items-center justify-between bg-base-100/80 backdrop-blur supports-[backdrop-filter]:bg-base-100/60">
          <div>
            <h2 className="text-2xl font-bold">Execute Flow</h2>
            <p className="text-base-content/70 mt-1">
              Review and confirm the flow execution settings
            </p>
          </div>
          <button
            onClick={onClose}
            className="btn btn-ghost btn-sm btn-square hover:rotate-90 transition-transform"
          >
            <Plus className="rotate-45" size={20} />
          </button>
        </div>

        <div className="flex-1 overflow-auto p-6">
          <div className="space-y-4">
            <div>
              <h3 className="font-medium mb-2">Flow Name</h3>
              <p className="text-base-content/80 font-mono">{flowName}.py</p>
            </div>

            <div>
              <h3 className="font-medium mb-2">Username</h3>
              <p className="text-base-content/80">{username}</p>
            </div>

            <div>
              <h3 className="font-medium mb-2">Chip ID</h3>
              <p className="text-base-content/80">{chipId}</p>
              <p className="mt-1 text-sm text-base-content/70">
                This workflow reserves the entire chip for all its steps. Other runs on this chip
                must wait until the workflow finishes.
              </p>
            </div>

            {description && (
              <div>
                <h3 className="font-medium mb-2">Description</h3>
                <p className="text-base-content/80">{description}</p>
              </div>
            )}

            {tagList.length > 0 && (
              <div>
                <h3 className="font-medium mb-2">Tags</h3>
                <div className="flex flex-wrap gap-2">
                  {tagList.map((tag, index) => (
                    <span key={index} className="px-2 py-1 bg-base-200 rounded text-sm">
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {disabledReason && (
          <div id={disabledReasonId} className="alert alert-info mx-6 mb-4" role="status">
            <span>{disabledReason}</span>
          </div>
        )}

        <div className="px-6 py-4 border-t border-base-300 flex justify-end gap-2">
          <button className="btn btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn btn-success"
            disabled={Boolean(disabledReason)}
            aria-describedby={disabledReason ? disabledReasonId : undefined}
            onClick={() => {
              if (!disabledReason) onConfirm();
            }}
          >
            Execute
          </button>
        </div>
      </div>
    </div>
  );
}
