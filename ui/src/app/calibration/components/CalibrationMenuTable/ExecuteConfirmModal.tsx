"use client";

import { useState } from "react";
import { BsPlus } from "react-icons/bs";
import type { Menu } from "../../model";

export function ExecuteConfirmModal({
  selectedItem,
  onConfirm,
  onCancel,
}: {
  selectedItem: Menu;
  onConfirm: (updatedItem: Menu) => void;
  onCancel: () => void;
}) {
  const [menu, setMenu] = useState(selectedItem);

  const handleConfirmClick = () => {
    onConfirm(menu);
  };

  return (
    <dialog open className="modal">
      <div className="modal-box max-w-3xl">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h3 className="text-2xl font-bold">Execute Calibration</h3>
            <p className="text-base-content/70 mt-1">
              Review and confirm the calibration settings
            </p>
          </div>
          <button
            onClick={onCancel}
            className="btn btn-ghost btn-sm btn-square hover:rotate-90 transition-transform"
          >
            <BsPlus className="text-xl rotate-45" />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <h3 className="font-medium mb-2">Name</h3>
            <p className="text-base-content/80">{menu.name}</p>
          </div>

          <div>
            <h3 className="font-medium mb-2">Description</h3>
            <p className="text-base-content/80">{menu.description}</p>
          </div>

          <div>
            <h3 className="font-medium mb-2">Qubit IDs</h3>
            <div className="space-y-1">
              {menu.qids.map((qidGroup, index) => (
                <p key={index} className="text-base-content/80">
                  Group {index + 1}: {qidGroup.join(", ")}
                </p>
              ))}
            </div>
          </div>

          {menu.tasks && menu.tasks.length > 0 && (
            <div>
              <h3 className="font-medium mb-2">Tasks</h3>
              <div className="space-y-1">
                {menu.tasks.map((task, index) => (
                  <p key={index} className="text-base-content/80">
                    {task}
                  </p>
                ))}
              </div>
            </div>
          )}

          {menu.tags && menu.tags.length > 0 && (
            <div>
              <h3 className="font-medium mb-2">Tags</h3>
              <div className="flex flex-wrap gap-2">
                {menu.tags.map((tag, index) => (
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

          <div>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                className="checkbox"
                checked={menu.notify_bool}
                onChange={(e) =>
                  setMenu({ ...menu, notify_bool: e.target.checked })
                }
              />
              <span>Notify on completion</span>
            </label>
          </div>
        </div>

        <div className="modal-action">
          <button className="btn btn-ghost" onClick={onCancel}>
            Cancel
          </button>
          <button className="btn btn-primary" onClick={handleConfirmClick}>
            Execute
          </button>
        </div>
      </div>
      <form method="dialog" className="modal-backdrop">
        <button onClick={onCancel}>close</button>
      </form>
    </dialog>
  );
}
