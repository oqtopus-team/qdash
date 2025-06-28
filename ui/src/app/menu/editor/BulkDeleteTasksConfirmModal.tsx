"use client";

import { BsPlus } from "react-icons/bs";

export function BulkDeleteTasksConfirmModal({
  taskNames,
  onConfirm,
  onClose,
}: {
  taskNames: string[];
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="bg-base-100 rounded-xl w-full max-w-lg overflow-hidden flex flex-col shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-6 py-4 border-b border-base-300 flex items-center justify-between bg-base-100/80 backdrop-blur supports-[backdrop-filter]:bg-base-100/60">
          <div>
            <h2 className="text-2xl font-bold">Delete Tasks</h2>
            <p className="text-base-content/70 mt-1">
              This action cannot be undone
            </p>
          </div>
          <button
            onClick={onClose}
            className="btn btn-ghost btn-sm btn-square hover:rotate-90 transition-transform"
          >
            <BsPlus className="text-xl rotate-45" />
          </button>
        </div>

        <div className="p-6">
          <p className="mb-4">
            Are you sure you want to delete the following {taskNames.length}{" "}
            tasks?
          </p>
          <div className="bg-base-200 rounded-lg p-3 max-h-48 overflow-y-auto">
            <ul className="list-disc list-inside space-y-1">
              {taskNames.map((name) => (
                <li key={name} className="text-sm">
                  {name}
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="px-6 py-4 border-t border-base-300 flex justify-end gap-2">
          <button className="btn btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button className="btn btn-error" onClick={onConfirm}>
            Delete {taskNames.length} tasks
          </button>
        </div>
      </div>
    </div>
  );
}
