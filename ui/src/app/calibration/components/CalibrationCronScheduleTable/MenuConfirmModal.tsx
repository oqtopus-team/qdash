"use client";

import { BsPlus } from "react-icons/bs";

import { ScheduleDisplay } from "./ScheduleDisplay";

import type { MenuModel } from "@/schemas";

interface MenuConfirmModalProps {
  menu: MenuModel;
  onConfirm: () => void;
  onCancel: () => void;
}

export function MenuConfirmModal({
  menu,
  onConfirm,
  onCancel,
}: MenuConfirmModalProps) {
  return (
    <dialog open className="modal">
      <div className="modal-box max-w-3xl">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h3 className="text-2xl font-bold">Menu Details</h3>
            <p className="text-base-content/70 mt-1">
              Review menu details before editing
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
            <h3 className="font-medium mb-2">Schedule</h3>
            <div className="space-y-1">
              <ScheduleDisplay schedule={menu.schedule} />
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
        </div>

        <div className="modal-action">
          <button className="btn btn-ghost" onClick={onCancel}>
            Cancel
          </button>
          <button className="btn btn-primary" onClick={onConfirm}>
            Edit Menu
          </button>
        </div>
      </div>
      <form method="dialog" className="modal-backdrop">
        <button onClick={onCancel}>close</button>
      </form>
    </dialog>
  );
}
