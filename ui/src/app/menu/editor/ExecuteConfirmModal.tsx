"use client";

import { useState } from "react";
import { BsPlus, BsLock } from "react-icons/bs";
import { toast } from "react-toastify";
import { GetMenuResponse } from "@/schemas";
import { useExecuteCalib } from "@/client/calibration/calibration";
import { useFetchExecutionLockStatus } from "@/client/execution/execution";
import { useAuth } from "@/app/contexts/AuthContext";

export function ExecuteConfirmModal({
  selectedMenu,
  onClose,
}: {
  selectedMenu: GetMenuResponse;
  onClose: () => void;
}) {
  const { user } = useAuth();
  const executeCalibMutation = useExecuteCalib();
  const [menu, setMenu] = useState(selectedMenu);

  const { data: lockStatus, isLoading: isLockStatusLoading } =
    useFetchExecutionLockStatus({
      query: {
        refetchInterval: 5000, // 5秒ごとに更新
      },
    });

  const isLocked = lockStatus?.data.lock ?? false;

  const handleConfirmClick = () => {
    if (isLocked) {
      toast.error(
        "実行がロックされています。他のキャリブレーションが完了するまでお待ちください。",
      );
      return;
    }

    executeCalibMutation.mutate(
      {
        data: {
          name: menu.name,
          username: user?.username ?? "default-user",
          description: menu.description,
          qids: menu.qids,
          notify_bool: menu.notify_bool,
          tasks: menu.tasks,
          tags: menu.tags,
          task_details: menu.task_details,
          batch_mode: menu.batch_mode,
        },
      },
      {
        onSuccess: (data) => {
          toast.success(
            <div>
              Calibration execution started!
              <br />
              <a
                href={data.data.qdash_ui_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary hover:underline"
              >
                View Details →
              </a>
            </div>,
          );
          onClose();
        },
        onError: (error) => {
          console.error("Error executing calibration:", error);
          toast.error("Error executing calibration");
        },
      },
    );
  };

  return (
    <div
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="bg-base-100 rounded-xl w-full max-w-3xl max-h-[90vh] overflow-hidden flex flex-col shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-6 py-4 border-b border-base-300 flex items-center justify-between bg-base-100/80 backdrop-blur supports-[backdrop-filter]:bg-base-100/60">
          <div>
            <h2 className="text-2xl font-bold">Execute Calibration</h2>
            <p className="text-base-content/70 mt-1">
              Review and confirm the calibration settings
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
        </div>

        <div className="px-6 py-4 border-t border-base-300 flex justify-end gap-2">
          <button className="btn btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button
            className={`btn ${isLocked ? "btn-disabled" : "btn-success"}`}
            onClick={handleConfirmClick}
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
