"use client";

import { useState } from "react";
import { toast } from "react-toastify";
import { BsPlus, BsTrash } from "react-icons/bs";
import { useCreateMenu, useListPreset } from "@/client/menu/menu";
import type { CreateMenuRequest } from "@/schemas";

const defaultFormData: CreateMenuRequest = {
  name: "",
  username: "",
  description: "",
  qids: [[""]],
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
    value: string | boolean | string[][] | string[]
  ) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  const handleQidsChange = (
    groupIndex: number,
    qubitIndex: number,
    value: string
  ) => {
    const newQids = [...formData.qids];
    if (!newQids[groupIndex]) {
      newQids[groupIndex] = [];
    }
    newQids[groupIndex][qubitIndex] = value;
    handleInputChange("qids", newQids);
  };

  const addQubitGroup = () => {
    handleInputChange("qids", [...formData.qids, [""]]);
  };

  const removeQubitGroup = (index: number) => {
    const newQids = formData.qids.filter((_, i) => i !== index);
    handleInputChange("qids", newQids);
  };

  const addQubitToGroup = (groupIndex: number) => {
    const newQids = [...formData.qids];
    newQids[groupIndex] = [...newQids[groupIndex], ""];
    handleInputChange("qids", newQids);
  };

  const removeQubitFromGroup = (groupIndex: number, qubitIndex: number) => {
    const newQids = [...formData.qids];
    newQids[groupIndex] = newQids[groupIndex].filter(
      (_, i) => i !== qubitIndex
    );
    if (newQids[groupIndex].length === 0) {
      removeQubitGroup(groupIndex);
    } else {
      handleInputChange("qids", newQids);
    }
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
        onError: (error) => {
          console.error("Error creating template item:", error);
          toast.error("Error creating template item");
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
                  setFormData(selectedPreset);
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

            {/* Qubit Groups */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <label className="label-text font-medium">Qubit Groups</label>
                <button
                  type="button"
                  onClick={addQubitGroup}
                  className="btn btn-sm btn-primary"
                >
                  Add Group
                </button>
              </div>

              <div className="space-y-4">
                {formData.qids.map((group, groupIndex) => (
                  <div key={groupIndex} className="card bg-base-200 p-4">
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-medium">
                        Group {groupIndex + 1}
                      </span>
                      <div className="flex gap-2">
                        <button
                          type="button"
                          onClick={() => addQubitToGroup(groupIndex)}
                          className="btn btn-sm btn-ghost"
                        >
                          Add Qubit
                        </button>
                        <button
                          type="button"
                          onClick={() => removeQubitGroup(groupIndex)}
                          className="btn btn-sm btn-ghost text-error"
                        >
                          <BsTrash />
                        </button>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {group.map((qubit, qubitIndex) => (
                        <div
                          key={qubitIndex}
                          className="flex items-center gap-2"
                        >
                          <input
                            type="text"
                            className="input input-bordered input-sm"
                            value={qubit}
                            onChange={(e) =>
                              handleQidsChange(
                                groupIndex,
                                qubitIndex,
                                e.target.value
                              )
                            }
                            placeholder={`Q${qubitIndex + 1}`}
                          />
                          <button
                            type="button"
                            onClick={() =>
                              removeQubitFromGroup(groupIndex, qubitIndex)
                            }
                            className="btn btn-sm btn-ghost text-error"
                          >
                            <BsTrash />
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>

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
