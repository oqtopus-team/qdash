"use client";

import { useState } from "react";
import { toast } from "react-toastify";
import { BsPlus } from "react-icons/bs";
import { useCreateMenu, useListPreset } from "@/client/menu/menu";
import type { CreateMenuRequest } from "@/schemas";
import type { CreateMenuRequestSchedule } from "@/schemas/createMenuRequestSchedule";
import { ScheduleInput } from "./ScheduleInput";

const defaultFormData: CreateMenuRequest = {
  name: "",
  username: "",
  description: "",
  schedule: {
    serial: [{ serial: [] }],
  } as CreateMenuRequestSchedule,
  notify_bool: false,
  tasks: [],
  tags: [],
};

export function CreateFromTemplateModal({
  onClose,
  onSuccess,
}: {
  onClose: () => void;
  onSuccess: () => void;
}) {
  const createMutation = useCreateMenu();
  const { data: presetData } = useListPreset();
  const [formData, setFormData] = useState<CreateMenuRequest>(defaultFormData);

  const handleInputChange = (
    field: keyof CreateMenuRequest,
    value: string | boolean | string[] | CreateMenuRequestSchedule
  ) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  const handleScheduleChange = (schedule: CreateMenuRequestSchedule) => {
    handleInputChange("schedule", schedule);
  };

  const handleTagsChange = (value: string) => {
    const tags = value
      .split(",")
      .map((tag) => tag.trim())
      .filter((tag) => tag !== "");
    handleInputChange("tags", tags);
  };

  const handleTasksChange = (value: string) => {
    const tasks = value
      .split(",")
      .map((task) => task.trim())
      .filter((task) => task !== "");
    handleInputChange("tasks", tasks);
  };

  const handleSaveClick = () => {
    createMutation.mutate(
      { data: formData },
      {
        onSuccess: () => {
          toast.success("Template item created successfully!");
          onSuccess();
          onClose();
        },
        onError: (error: any) => {
          console.error("Error creating template item:", error);
          const errorMessage =
            error.response?.data?.detail || "Error creating template item";
          toast.error(errorMessage);
        },
      }
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
        <div className="px-6 py-4 border-b border-base-300 flex flex-col gap-4 bg-base-100/80 backdrop-blur supports-[backdrop-filter]:bg-base-100/60">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-2xl font-bold">Create Menu</h2>
              <p className="text-base-content/70 mt-1">
                Fill in the form below to create a new menu
              </p>
            </div>
            <button
              onClick={onClose}
              className="btn btn-ghost btn-sm btn-square hover:rotate-90 transition-transform"
            >
              <BsPlus className="text-xl rotate-45" />
            </button>
          </div>

          <div className="flex items-center gap-4">
            <select
              className="select select-bordered w-full"
              onChange={(e) => {
                if (e.target.value === "") {
                  setFormData(defaultFormData);
                  return;
                }
                const selectedPreset = presetData?.data.menus.find(
                  (menu) => menu.name === e.target.value
                );
                if (selectedPreset) {
                  // Convert schedule format if needed
                  const schedule = selectedPreset.schedule || {
                    serial: [{ serial: [] }],
                  };
                  const tasks = selectedPreset.tasks || [];
                  setFormData({
                    ...selectedPreset,
                    schedule,
                    tasks,
                  });
                }
              }}
            >
              <option value="">Select a preset...</option>
              {presetData?.data.menus.map((menu) => (
                <option key={menu.name} value={menu.name}>
                  {menu.name} - {menu.description}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex-1 overflow-auto p-6">
          <div className="space-y-6">
            {/* Basic Information */}
            <div className="space-y-4">
              <div className="form-control">
                <label className="label">
                  <span className="label-text">Name</span>
                </label>
                <input
                  type="text"
                  className="input input-bordered w-full"
                  value={formData.name}
                  onChange={(e) => handleInputChange("name", e.target.value)}
                  placeholder="Enter menu name"
                />
              </div>

              <div className="form-control">
                <label className="label">
                  <span className="label-text">Username</span>
                </label>
                <input
                  type="text"
                  className="input input-bordered w-full"
                  value={formData.username}
                  onChange={(e) =>
                    handleInputChange("username", e.target.value)
                  }
                  placeholder="Enter username"
                />
              </div>

              <div className="form-control">
                <label className="label">
                  <span className="label-text">Description</span>
                </label>
                <textarea
                  className="textarea textarea-bordered w-full"
                  value={formData.description}
                  onChange={(e) =>
                    handleInputChange("description", e.target.value)
                  }
                  placeholder="Enter description"
                />
              </div>
            </div>

            {/* Schedule */}
            <ScheduleInput
              value={formData.schedule}
              onChange={handleScheduleChange}
            />

            {/* Tasks */}
            <div className="form-control">
              <label className="label">
                <span className="label-text">Tasks (comma-separated)</span>
              </label>
              <input
                type="text"
                className="input input-bordered w-full"
                value={formData.tasks?.join(", ") || ""}
                onChange={(e) => handleTasksChange(e.target.value)}
                placeholder="task1, task2, task3"
              />
            </div>

            {/* Tags */}
            <div className="form-control">
              <label className="label">
                <span className="label-text">Tags (comma-separated)</span>
              </label>
              <input
                type="text"
                className="input input-bordered w-full"
                value={formData.tags?.join(", ") || ""}
                onChange={(e) => handleTagsChange(e.target.value)}
                placeholder="tag1, tag2, tag3"
              />
            </div>

            {/* Notify */}
            <div className="form-control">
              <label className="label cursor-pointer">
                <span className="label-text">Enable Notifications</span>
                <input
                  type="checkbox"
                  className="toggle"
                  checked={formData.notify_bool || false}
                  onChange={(e) =>
                    handleInputChange("notify_bool", e.target.checked)
                  }
                />
              </label>
            </div>
          </div>
        </div>

        <div className="px-6 py-4 border-t border-base-300 flex justify-end gap-2">
          <button className="btn btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn btn-primary"
            onClick={handleSaveClick}
            disabled={!formData.name || !formData.username}
          >
            Create
          </button>
        </div>
      </div>
    </div>
  );
}
