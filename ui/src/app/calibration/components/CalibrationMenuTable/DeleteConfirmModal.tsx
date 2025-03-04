"use client";

import { BsPlus } from "react-icons/bs";
import type { Menu } from "../../model";

export function DeleteConfirmModal({
  selectedItem,
  onConfirm,
  onCancel,
}: {
  selectedItem: Menu;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 backdrop-blur-sm p-4"
      onClick={onCancel}
    >
      <div
        className="bg-base-100 rounded-xl w-full max-w-lg overflow-hidden flex flex-col shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-6 py-4 border-b border-base-300 flex items-center justify-between bg-base-100/80 backdrop-blur supports-[backdrop-filter]:bg-base-100/60">
          <div>
            <h2 className="text-2xl font-bold">Delete Menu</h2>
            <p className="text-base-content/70 mt-1">
              This action cannot be undone
            </p>
          </div>
          <button
            onClick={onCancel}
            className="btn btn-ghost btn-sm btn-square hover:rotate-90 transition-transform"
          >
            <BsPlus className="text-xl rotate-45" />
          </button>
        </div>

        <div className="p-6">
          <p>
            Are you sure you want to delete the menu{" "}
            <span className="font-semibold">{selectedItem.name}</span>?
          </p>
        </div>

        <div className="px-6 py-4 border-t border-base-300 flex justify-end gap-2">
          <button className="btn btn-ghost" onClick={onCancel}>
            Cancel
          </button>
          <button className="btn btn-error" onClick={onConfirm}>
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}
