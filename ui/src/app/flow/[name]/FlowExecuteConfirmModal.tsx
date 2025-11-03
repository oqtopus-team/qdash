"use client";

import { BsPlus, BsLock } from "react-icons/bs";

interface FlowExecuteConfirmModalProps {
  flowName: string;
  username: string;
  chipId: string;
  description: string;
  tags: string;
  isLocked: boolean;
  isLockStatusLoading: boolean;
  onConfirm: () => void;
  onClose: () => void;
}

export function FlowExecuteConfirmModal({
  flowName,
  username,
  chipId,
  description,
  tags,
  isLocked,
  isLockStatusLoading,
  onConfirm,
  onClose,
}: FlowExecuteConfirmModalProps) {
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
            <BsPlus className="text-xl rotate-45" />
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
                    <span
                      key={index}
                      className="px-2 py-1 bg-base-200 rounded text-sm"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {isLocked && (
              <div className="alert alert-warning">
                <BsLock className="h-5 w-5" />
                <span>
                  Execution is locked. Another calibration is currently running.
                  Please wait until it completes.
                </span>
              </div>
            )}
          </div>
        </div>

        <div className="px-6 py-4 border-t border-base-300 flex justify-end gap-2">
          <button className="btn btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button
            className={`btn ${isLocked ? "btn-disabled" : "btn-success"}`}
            onClick={onConfirm}
            disabled={isLocked || isLockStatusLoading}
          >
            {isLocked ? (
              <>
                <BsLock className="mr-2" />
                Locked
              </>
            ) : (
              "Execute"
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
