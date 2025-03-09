"use client";

import { useEffect, useState } from "react";
import type { MenuModel, ScheduleCronCalibResponse } from "@/schemas";
import { useScheduleCronCalib } from "@/client/calibration/calibration";

interface EditScheduleModalProps {
  isOpen: boolean;
  onClose: () => void;
  schedule: ScheduleCronCalibResponse;
  menus: MenuModel[];
  onSuccess: () => void;
}

export function EditScheduleModal({
  isOpen,
  onClose,
  schedule,
  menus,
  onSuccess,
}: EditScheduleModalProps) {
  const [schedulerName, setSchedulerName] = useState(schedule.scheduler_name);
  const [menuName, setMenuName] = useState(schedule.menu_name);
  const [cron, setCron] = useState(schedule.cron);

  const scheduleMutation = useScheduleCronCalib();

  useEffect(() => {
    if (isOpen) {
      setSchedulerName(schedule.scheduler_name);
      setMenuName(schedule.menu_name);
      setCron(schedule.cron);
    }
  }, [isOpen, schedule]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    scheduleMutation.mutate(
      {
        data: {
          scheduler_name: schedulerName,
          menu_name: menuName,
          cron: cron,
          active: schedule.active,
        },
      },
      {
        onSuccess: () => {
          onSuccess();
          onClose();
        },
        onError: (error: Error) => {
          console.error("Error updating cron schedule:", error);
        },
      },
    );
  };

  if (!isOpen) return null;

  return (
    <dialog className="modal modal-open">
      <div className="modal-box">
        <h3 className="font-bold text-lg mb-4">Edit Cron Schedule</h3>
        <form onSubmit={handleSubmit}>
          <div className="form-control w-full">
            <label className="label">
              <span className="label-text">Menu Name</span>
            </label>
            <select
              className="select select-bordered w-full"
              value={menuName}
              onChange={(e) => setMenuName(e.target.value)}
              required
            >
              <option value="">Select Menu</option>
              {menus.map((menu) => (
                <option key={menu.name} value={menu.name}>
                  {menu.name}
                </option>
              ))}
            </select>
          </div>
          <div className="form-control w-full">
            <label className="label">
              <span className="label-text">Cron Expression</span>
            </label>
            <input
              type="text"
              className="input input-bordered w-full"
              value={cron}
              onChange={(e) => setCron(e.target.value)}
              required
            />
          </div>
          <div className="modal-action">
            <button type="button" className="btn" onClick={onClose}>
              Cancel
            </button>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={scheduleMutation.isPending}
            >
              {scheduleMutation.isPending ? (
                <span className="loading loading-spinner loading-sm"></span>
              ) : (
                "Save"
              )}
            </button>
          </div>
        </form>
      </div>
      <div className="modal-backdrop" onClick={onClose}></div>
    </dialog>
  );
}
